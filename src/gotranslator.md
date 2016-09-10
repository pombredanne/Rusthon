Go Translator
-------------

note: The GoGenerator class subclasses from javascript generator.


```python

go_types = 'bool string int float64'.split()

class GoGenerator( JSGenerator ):
	def __init__(self, source=None, requirejs=False, insert_runtime=False):
		assert source
		JSGenerator.__init__(self, source=source, requirejs=False, insert_runtime=False)

		self._go = True
		self._dart = False
		self._class_stack = list()
		self._classes = dict()		## name : node
		#	node._parents = set()
		#	node._struct_def = dict()
		#	node._subclasses = set()  ## required for generics generator
		#	## subclasses must be a struct union so that Go can convert between struct types
		#	node._subclasses_union = dict()
		self.method_returns_multiple_subclasses = dict() # class name : method name that can return multiple subclass types
		self._class_props = dict()

		self._vars = set()
		self._known_vars = set()
		self._kwargs_type_ = dict()

		self._imports = set()
		self._ids = 0
		self._known_instances = dict()
		self._known_arrays    = dict()
		self._known_maps      = dict()
		self._scope_stack = list()

		self.interfaces = dict()  ## for Go backend, TODO unify Go/Rust/C++ logic
		self.uids = 0
		self.unodes = dict()

		self._slice_hack_id = 0

	def uid(self):
		self.uids += 1
		return self.uids


	def visit_Import(self, node):
		r = [alias.name.replace('__SLASH__', '/') for alias in node.names]
		res = []
		if r:
			for name in r:
				self._imports.add('import("%s");' %name)

		if res:
			return '\n'.join(res)
		else:
			return ''

	def visit_Str(self, node):
		s = node.s.replace("\\", "\\\\").replace('\n', '\\n').replace('\r', '\\r').replace('"', '\\"')
		return '"%s"' % s

	def visit_Is(self, node):
		return '=='
	def visit_IsNot(self, node):
		return '!='

	def visit_If(self, node):
		out = []
		test = self.visit(node.test)
		if test.startswith('(') and test.endswith(')'):
			out.append( 'if %s {' %test )
		else:
			out.append( 'if (%s) {' %test )

		self.push()

		for line in list(map(self.visit, node.body)):
			if line is None: continue
			out.append( self.indent() + line )

		orelse = []
		for line in list(map(self.visit, node.orelse)):
			orelse.append( self.indent() + line )

		self.pull()

		if orelse:
			out.append( self.indent() + '} else {')
			out.extend( orelse )

		out.append( self.indent() + '}' )

		return '\n'.join( out )

	def visit_Name(self, node):
		if node.id == 'None':
			return 'nil'
		elif node.id == 'True':
			return 'true'
		elif node.id == 'False':
			return 'false'
		#elif node.id == 'null':
		#	return 'nil'
		return node.id

	def get_subclasses( self, C ):
		'''
		returns all sibling subclasses, C can be a subclass or the base class
		'''
		subclasses = set()
		self._collect_subclasses(C, subclasses)
		return subclasses

	def _collect_subclasses(self, C, subclasses):
		node = self._classes[ C ]
		if len(node._parents)==0:
			for sub in node._subclasses:
				subclasses.add( sub )
		else:
			for parent in node._parents:
				self._collect_subclasses(parent, subclasses)


	def visit_ClassDef(self, node):
		self._class_stack.append( node )
		if not hasattr(node, '_parents'):  ## only setup on the first pass
			node._parents = set()
			node._struct_def = dict()
			node._subclasses = set()  ## required for generics generator
			## subclasses must be a struct union so that Go can convert between struct types
			node._subclasses_union = dict()

		out = []
		sdef = dict()
		props = set()
		bases = set()
		base_classes = set()

		self._classes[ node.name ] = node
		self._class_props[ node.name ] = props
		if node.name not in self.method_returns_multiple_subclasses:
			self.method_returns_multiple_subclasses[ node.name ] = set()
		
		self.interfaces[ node.name ] = set()


		for base in node.bases:
			n = self.visit(base)
			if n == 'object':
				continue
			node._parents.add( n )

			bases.add( n )
			if n in self._class_props:
				props.update( self._class_props[n] )
				base_classes.add( self._classes[n] )
			#else:  ## special case - subclassing a builtin like `list`
			#	continue

			for p in self._classes[ n ]._parents:
				bases.add( p )
				props.update( self._class_props[p] )
				base_classes.add( self._classes[p] )

			self._classes[ n ]._subclasses.add( node.name )


		for decor in node.decorator_list:  ## class decorators
			if isinstance(decor, ast.Call):
				assert decor.func.id=='__struct__'
				#props.update( [self.visit(a) for a in decor.args] )
				for kw in decor.keywords:
					props.add( kw.arg )
					T = kw.value.id
					if T == 'interface': T = 'interface{}'
					sdef[ kw.arg ] = T


		init = None
		method_names = set()
		for b in node.body:
			if isinstance(b, ast.FunctionDef):
				method_names.add( b.name )
				if b.name == '__init__':
					init = b
			elif isinstance(b, ast.Expr) and isinstance(b.value, ast.Dict):
				for i in range( len(b.value.keys) ):
					k = self.visit( b.value.keys[ i ] )
					if isinstance(b.value.values[i], ast.Str):
						v = b.value.values[i].s
					else:
						v = self.visit( b.value.values[i] )
					if v == 'interface': v = 'interface{}'
					sdef[k] = v

		for k in sdef:
			v = sdef[k]
			if v=='interface{}':
				self.interfaces[node.name].add(k)

		node._struct_def.update( sdef )
		unionstruct = dict()
		unionstruct.update( sdef )
		for pname in node._parents:
			parent = self._classes[ pname ]
			parent._subclasses_union.update( sdef )        ## first pass
			unionstruct.update( parent._subclasses_union ) ## second pass


		parent_init = None
		if base_classes:
			for bnode in base_classes:
				for b in bnode.body:
					if isinstance(b, ast.FunctionDef):
						if b.name in method_names:
							self.catch_call.add( '%s.%s' %(bnode.name, b.name))
							n = b.name
							b.name = '%s_%s'%(bnode.name, b.name)
							out.append( self.visit(b) )
							b.name = n
							continue
						if b.name == '__init__':
							parent_init = {'class':bnode, 'init':b}
							#continue
						out.append( self.visit(b) )


		out.append( 'type %s struct {' %node.name)
		if len(node._parents)==0:
			out.append('__object__')

		if base_classes:
			for bnode in base_classes:
				## Go only needs the name of the parent struct and all its items are inserted automatically ##
				out.append('%s' %bnode.name)
				## Go allows multiple a variable to redefined by the sub-struct,
				## but this can throw an error: `invalid operation: ambiguous selector`
				## removing the duplicate name here fixes that error.
				for key in bnode._struct_def.keys():
					#if key in sdef:
					#	sdef.pop(key)
					if key in unionstruct:
						unionstruct.pop(key)

		#for name in sdef:
		#	out.append('%s %s' %(name, sdef[name]))
		for name in unionstruct:
			out.append('%s %s' %(name, unionstruct[name]))
		out.append('}')


		for b in node.body:
			if isinstance(b, ast.FunctionDef):
				out.append( self.visit(b) )

		if init or parent_init:
			if parent_init:
				classname = parent_init['class'].name
				init = parent_init['init']
			else:
				classname = node.name

			out.append( 'func __new__%s( %s ) *%s {' %(node.name, init._args_signature, node.name))
			out.append( '  ob := %s{}' %node.name )
			out.append( '  ob.__init__(%s)' %','.join(init._arg_names))
			## used by generics to workaround the problem that a super method that returns `self`,
			## may infact return wrong subclass type, because a struct to return that is not of type
			## self will be cast to self - while this is ok if just reading attributes from it,
			## it fails with method calls, because the casting operation on the struct changes its
			## method pointers.  by storing the class name on the instance, it can be used in a generics
			## type switch to get to the real class and call the right methods.
			out.append( '  ob.__class__ = "%s"' %node.name)
			out.append( '  return &ob')
			out.append('}')

		else:
			#out.append( 'func __new__%s() *%s { return &%s{} }' %(node.name, node.name, node.name))
			out.append( 'func __new__%s() *%s {' %(node.name, node.name))
			out.append( '  ob := %s{}' %node.name )
			out.append( '  ob.__class__ = "%s"' %node.name)
			out.append( '  return &ob')
			out.append('}')



		self.catch_call = set()
		self._class_stack.pop()
		return '\n'.join(out)


	def _visit_call_special( self, node ):
		fname = self.visit(node.func)
		assert fname in self.catch_call
		assert len(self._class_stack)
		if len(node.args):
			if isinstance(node.args[0], ast.Name) and node.args[0].id == 'self':
				node.args.remove( node.args[0] )

		#name = '_%s_' %self._class_stack[-1].name
		name = 'self.'
		name += fname.replace('.', '_')
		return self._visit_call_helper(node, force_name=name)


	def visit_Subscript(self, node):
		if isinstance(node.slice, ast.Ellipsis):
			raise NotImplementedError( 'ellipsis')
		else:
			## deference pointer and then index
			if isinstance(node.slice, ast.Slice):
				r = '&(*%s)[%s]' % (self.visit(node.value), self.visit(node.slice))
			else:
				r = '(*%s)[%s]' % (self.visit(node.value), self.visit(node.slice))

			#if isinstance(node.value, ast.Name) and node.value.id in self._known_arrays:
			#	target = node.value.id
			#	#value = self.visit( node.value )
			#	cname = self._known_arrays[target]
			#	#raise GenerateGenericSwitch( {'target':target, 'value':r, 'class':cname} )
			#	raise GenerateGenericSwitch( {'value':r, 'class':cname} )

			return r



	def visit_Slice(self, node):
		lower = upper = step = None
		if node.lower:
			lower = self.visit(node.lower)
		if node.upper:
			upper = self.visit(node.upper)
		if node.step:
			step = self.visit(node.step)

		if lower and upper:
			return '%s:%s' %(lower,upper)
		elif upper:
			return ':%s' %upper
		elif lower:
			return '%s:'%lower
		else:
			raise SyntaxError('TODO slice')


	def visit_Print(self, node):
		r = []
		for e in node.values:
			s = self.visit(e)
			if s is None: raise RuntimeError(e)
			if isinstance(e, ast.List):
				r.append('fmt.Println(%s);' %s[1:-1])
			else:
				r.append('fmt.Println(%s);' %s)
		return ''.join(r)

	def visit_Expr(self, node):
		return self.visit(node.value)


	def visit_Module(self, node):
		header = [
			'package main',
			'import "fmt"',
			#'import "reflect"'
		]
		lines = []

		for b in node.body:
			line = self.visit(b)

			if line:
				for sub in line.splitlines():
					if sub==';':
						raise SyntaxError(line)
					else:
						lines.append( sub )
			else:
				if isinstance(b, ast.Import):
					pass
				elif isinstance(b, ast.ImportFrom):
					pass
				else:
					raise SyntaxError(b)

		lines.append('type _kwargs_type_ struct {')
		for name in self._kwargs_type_:
			type = self._kwargs_type_[name]
			lines.append( '  %s %s' %(name,type))
			lines.append( '  __use__%s bool' %name)
		lines.append('}')

		lines = header + list(self._imports) + lines
		return '\n'.join( lines )


	def visit_Compare(self, node):
		comp = [ '(']
		comp.append( self.visit(node.left) )
		comp.append( ')' )

		for i in range( len(node.ops) ):
			comp.append( self.visit(node.ops[i]) )

			if isinstance(node.comparators[i], ast.BinOp):
				comp.append('(')
				comp.append( self.visit(node.comparators[i]) )
				comp.append(')')
			else:
				comp.append( self.visit(node.comparators[i]) )

		return ' '.join( comp )

	def visit_For(self, node):
		target = self.visit(node.target)
		lines = []
		if isinstance(node.iter, ast.Call) and isinstance(node.iter.func, ast.Name):

			if node.iter.func.id == 'range':
				if len(node.iter.args)==1:
					iter = self.visit(node.iter.args[0])
					lines.append('for %s := 0; %s < %s; %s++ {' %(target, target, iter, target))
				elif len(node.iter.args)==2:
					start = self.visit(node.iter.args[0])
					iter = self.visit(node.iter.args[1])
					lines.append('for %s := %s; %s < %s; %s++ {' %(target, start, target, iter, target))
				else:
					raise SyntaxError('invalid for range loop')

			elif node.iter.func.id == 'enumerate':
				iter = self.visit(node.iter.args[0])
				idx = self.visit(node.target.elts[0])
				tar = self.visit(node.target.elts[1])
				lines.append('for %s,%s := range *%s {' %(idx,tar, iter))

			else: ## generator function
				gfunc = node.iter.func.id
				gargs = ','.join( [self.visit(e) for e in node.iter.args] )
				lines.append('__gen%s := __new__%s(%s)' %(gfunc,gfunc, gargs))
				lines.append('for __gen%s.__done__ != 1 {' %gfunc)
				lines.append('	%s := __gen%s.next()' %(self.visit(node.target), gfunc))

		elif isinstance(node.target, ast.List) or isinstance(node.target, ast.Tuple):
			iter = self.visit( node.iter )
			key = self.visit(node.target.elts[0])
			val = self.visit(node.target.elts[1])
			lines.append('for %s,%s := range *%s {' %(key,val, iter))

		else:
			iter = self.visit( node.iter )
			lines.append('for _,%s := range *%s {' %(target, iter))

		self.push()
		for b in node.body:
			lines.append( self.indent()+self.visit(b) )
		self.pull()
		lines.append( self.indent()+'}' )  ## end of for loop
		return '\n'.join(lines)


	def _visit_call_helper(self, node, force_name=None):
		fname = force_name or self.visit(node.func)
		is_append = False
		if fname.endswith('.append'):
			is_append = True
			arr = fname.split('.append')[0]
		####################################
		if fname=='main':  ## can not directly call `main` in Go
			return '/*run main*/'
		elif fname == '__arg_array__':
			assert len(node.args)==1
			T = self.parse_go_style_arg(node.args[0])
			if self.is_prim_type(T):
				return '*[]%s' %T
			else:
				return '*[]*%s' %T

		elif fname=='__let__':
			if len(node.args) and isinstance(node.args[0], ast.Attribute): ## syntax `let self.x:T = y`
				assert node.args[0].value.id == 'self'
				assert len(node.args)==3
				T = None
				value = self.visit(node.args[2])
				if isinstance(node.args[1], ast.Str):
					T = node.args[1].s
				else:
					T = self.visit(node.args[1])

				return 'self.%s = %s' %(node.args[0].attr, self.visit(node.args[2]))
			else:
				raise RuntimeError('TODO let...')


		elif fname == 'range':  ## hack to support range builtin, translates to `range1,2,3`
			assert len(node.args)
			fname += str(len(node.args))
		elif fname == 'len':
			return 'len(*%s)' %self.visit(node.args[0])
		elif fname == 'go.type_assert':
			raise RuntimeError('go.type_assert is deprecated')
			val = self.visit(node.args[0])
			type = self.visit(node.args[1])
			raise GenerateTypeAssert( {'type':type, 'value':val} )
			## below is deprecated
			if type == 'self':
				## todo how to better mark interfaces, runtime type switch?
				if '.' in type and type.split('.')[0]=='self' and type.split('.')[-1] in self.interfaces[self._class_stack[-1].name]:
					val += '.(%s)' %self._class_stack[-1].name
					return '&%s(%s)' %(type, val )
				else:
					type = '&' + self._class_stack[-1].name
			else:
				type = '*' + type  ## TODO tests - should this be &
			#return 'interface{}(%s).(%s)' %(self.visit(node.args[0]), type)


			return '%s(*%s)' %(type, val )


		if node.args:
			args = [self.visit(e) for e in node.args]
			args = ', '.join([e for e in args if e])
		else:
			args = ''

		if node.keywords:
			if args: args += ','
			args += '_kwargs_type_{'
			x = ['%s:%s' %(kw.arg,self.visit(kw.value)) for kw in node.keywords]
			x.extend( ['__use__%s:true' %kw.arg for kw in node.keywords] )
			args += ','.join( x )
			args += '}'

		if node.starargs:
			if args: args += ','
			args += '*%s...' %self.visit(node.starargs)

		if is_append:
			## deference pointer as first arg to append, assign to temp variable, then set the pointer to the new array.
			id = self._ids
			self._ids += 1
			item = args

			if item in self._known_instances:
				classname = self._known_instances[ item ]
				#raise SyntaxError( self._known_instances[item] )
				#if arr in self._known_vars:
				#	raise SyntaxError('kow')
				if arr in self._known_arrays and classname != self._known_arrays[arr]:
					#raise SyntaxError( self._known_arrays[arr])
					item = '%s(*%s)' %(self._known_arrays[arr], item)
					r = '__addr%s := %s;' %(id,item)
					return r + '__%s := append(*%s,&__addr%s); *%s = __%s;' % (id, arr, id, arr, id)

			return '__%s := append(*%s,%s); *%s = __%s;' % (id, arr, item, arr, id)

		else:

			if isinstance(node.func, ast.Attribute) and False:
				if isinstance(node.func.value, ast.Name):
					varname = node.func.value.id
					if varname in self._known_vars:
						#raise SyntaxError(varname + ' is known class::' + self._known_instances[varname] + '%s(%s)' % (fname, args))
						cname = self._known_instances[varname]
						if node.func.attr in self.method_returns_multiple_subclasses[ cname ]:
							raise SyntaxError('%s(%s)' % (fname, args))

			if fname in self._classes:
				fname = '__new__%s' %fname

			return '%s(%s)' % (fname, args)


	def visit_Assert(self, node):
		return 'if ((%s) == false) { panic("assertion failed"); }' %self.visit(node.test)


	def visit_BinOp(self, node):
		left = self.visit(node.left)
		op = self.visit(node.op)
		right = self.visit(node.right)

		if op == '>>' and left == '__new__':
			## calls generated class constructor: user example `new MyClass()` ##
			## for rare cases where the translator is not aware of some transpiled class ##
			if not right.startswith('__new__'):
				return '__new__%s' %right
			else:
				return right

		elif op == '<<':
			if left in ('__go__receive__', '__go__send__'):
				return '<- %s' %right
			elif isinstance(node.left, ast.Call) and isinstance(node.left.func, ast.Name) and node.left.func.id in ('__go__array__', '__go__arrayfixed__', '__go__map__', '__go__func__'):
				if node.left.func.id == '__go__func__':
					raise SyntaxError('TODO - go.func')
				elif node.left.func.id == '__go__map__':
					key_type = self.visit(node.left.args[0])
					value_type = self.visit(node.left.args[1])
					if value_type == 'interface': value_type = 'interface{}'
					return '&map[%s]%s%s' %(key_type, value_type, right)
				else:
					if not right.startswith('{') and not right.endswith('}'):
						right = '{%s}' %right[1:-1]

					if node.left.func.id == '__go__array__':
						T = self.visit(node.left.args[0])
						if T in go_types:
							return '&[]%s%s' %(T, right)
						else:
							self._catch_assignment = {'class':T}  ## visit_Assign catches this
							return '&[]*%s%s' %(T, right)
					elif node.left.func.id == '__go__arrayfixed__':
						asize = self.visit(node.left.args[0])
						atype = self.visit(node.left.args[1])
						if atype not in go_types:
							if right != '{}': raise SyntaxError('todo init array of objects with args')
							return '&make([]*%s, %s)' %(atype, asize)
						else:
							return '&[%s]%s%s' %(asize, atype, right)
			elif isinstance(node.left, ast.Name) and node.left.id=='__go__array__' and op == '<<':
				return '*[]%s' %self.visit(node.right)

		if left in self._typed_vars and self._typed_vars[left] == 'numpy.float32':
			left += '[_id_]'
		if right in self._typed_vars and self._typed_vars[right] == 'numpy.float32':
			right += '[_id_]'

		return '(%s %s %s)' % (left, op, right)

	def visit_Return(self, node):
		if isinstance(node.value, ast.Tuple):
			return 'return %s' % ', '.join(map(self.visit, node.value.elts))
		if node.value:
			try:
				v = self.visit(node.value)
			except GenerateTypeAssert as err:
				G = err[0]
				type = G['type']
				if type == 'self':
					type = self._class_stack[-1].name


				## This hack using reflect will not work for either case where the value
				## maybe an empty interface, or a pointer to a struct, because it is known
				## to the Go compiler if the value is an interface or pointer to struct,
				## and will not allow the alternate case.
				## case struct pointer:  invalid type assertion: __unknown__.(*A) (non-interface type *A on left)
				## case empty interface: cannot convert __unknown__ (type interface {}) to type B: need type assertion
				#out = [
				#	'__unknown__ := %s' %G['value'],
				#	'switch reflect.TypeOf(__unknown__).Kind() {',
				#	' case reflect.Interface:',
				#	'    __addr := __unknown__.(*%s)' %type,
				#	'    return __addr',
				#	' case reflect.Ptr:',
				#	'    __addr := %s(__unknown__)' %type,
				#	'    return __addr',
				#	'}'
				#]

				if not hasattr(node.value, 'uid'):
					node.value.uid = self.uid()

				id = '__magic__%s' % node.value.uid
				if id not in self.unodes: self.unodes[ id ] = node.value

				if hasattr(node.value, 'is_struct_pointer'):

					out = [
						'%s := %s( *%s )' %(id, type, G['value']),
						'return &%s' %id,
					]
				else:
					out = [
						'%s := %s.( *%s )' %(id, G['value'], type),
						'return %s' %id,
					]

				return '\n'.join(out)



			if v.startswith('&'):
				return '_hack := %s; return &_hack' %v[1:]
			else:
				return 'return %s' % v
		return 'return'

	def _visit_function(self, node):
		is_closure = False
		if self._function_stack[0] is node:
			self._vars = set()
			self._known_vars = set()
			self._known_instances = dict()
			self._known_arrays    = dict()


		elif len(self._function_stack) > 1:
			## do not clear self._vars and _known_vars inside of closure
			is_closure = True

		args_typedefs = {}
		chan_args_typedefs = {}
		return_type = None
		generic_base_class = None
		generics = set()
		args_generics = dict()
		returns_self = False
		use_generics = False

		for decor in node.decorator_list:
			if isinstance(decor, ast.Name) and decor.id=='generic':
				use_generics = True


		for decor in node.decorator_list:
			if isinstance(decor, ast.Call) and isinstance(decor.func, ast.Name) and decor.func.id == '__typedef__':
				for key in decor.keywords:
					if isinstance( key.value, ast.Str):
						args_typedefs[ key.arg ] = key.value.s
					else:
						args_typedefs[ key.arg ] = self.visit(key.value)

					## check for super classes - generics ##
					if use_generics and args_typedefs[ key.arg ] in self._classes:
						if node.name=='__init__':
							## generics type switch is not possible in __init__ because
							## it is used to generate the type struct, where types are static.
							## as a workaround generics passed to init always become `interface{}`
							args_typedefs[ key.arg ] = 'interface{}'
							#self._class_stack[-1]._struct_def[ key.arg ] = 'interface{}'
						else:
							classname = args_typedefs[ key.arg ]
							generic_base_class = classname
							generics.add( classname ) # switch v.(type) for each
							generics = generics.union( self._classes[classname]._subclasses )
							args_typedefs[ key.arg ] = 'interface{}'
							args_generics[ key.arg ] = classname

			elif isinstance(decor, ast.Call) and isinstance(decor.func, ast.Name) and decor.func.id == '__typedef_chan__':
				for key in decor.keywords:
					if isinstance(key.value, ast.Str):
						chan_args_typedefs[ key.arg ] = key.value.s.strip()
					else:
						chan_args_typedefs[ key.arg ] = self.visit(key.value)
			elif isinstance(decor, ast.Call) and isinstance(decor.func, ast.Name) and decor.func.id == 'returns':
				if decor.keywords:
					raise SyntaxError('invalid go return type')
				elif isinstance(decor.args[0], ast.Name):
					return_type = decor.args[0].id
				else:
					return_type = decor.args[0].s

				if return_type == 'self':
					return_type = '*' + self._class_stack[-1].name
					returns_self = True
					self.method_returns_multiple_subclasses[ self._class_stack[-1].name ].add(node.name)

		if return_type and not self.is_prim_type(return_type):
			if not return_type.startswith('*') and not return_type.startswith('&') and not return_type.startswith('func('):
				return_type = '*'+return_type

		node._arg_names = args_names = []
		args = []
		oargs = []
		offset = len(node.args.args) - len(node.args.defaults)
		varargs = False
		varargs_name = None
		is_method = False
		for i, arg in enumerate(node.args.args):
			arg_name = arg.id

			if arg_name not in args_typedefs.keys()+chan_args_typedefs.keys():
				if arg_name=='self':
					assert i==0
					is_method = True
					continue
				else:
					err = 'error in function: %s' %node.name
					err += '\n  missing typedef: %s' %arg.id
					raise SyntaxError(err)

			if arg_name in args_typedefs:
				arg_type = args_typedefs[arg_name]
				#if generics and (i==0 or (is_method and i==1)):
				if use_generics and generics and arg_name in args_generics.keys():  ## TODO - multiple generics in args
					a = '__gen__ %s' %arg_type
				elif self.is_prim_type(arg_type):
					a = '%s %s' %(arg_name, arg_type)
				elif not arg_type.startswith('*') and not arg_type.startswith('&') and not arg_type.startswith('func('):
					## assume pointer ##
					a = '%s *%s' %(arg_name, arg_type)
				else:
					a = '%s %s' %(arg_name, arg_type)
			else:
				arg_type = chan_args_typedefs[arg_name]
				if arg_type.startswith('Sender<'):
					arg_type = arg_type[ len('Sender<') : -1 ]
				elif arg_type.startswith('Receiver<'):
					arg_type = arg_type[ len('Receiver<') : -1 ]
				a = '%s chan %s' %(arg_name, arg_type)

			dindex = i - offset


			if dindex >= 0 and node.args.defaults:
				default_value = self.visit( node.args.defaults[dindex] )
				self._kwargs_type_[ arg_name ] = arg_type
				oargs.append( (arg_name, default_value) )
			else:
				args.append( a )
				node._arg_names.append( arg_name )

		##############################################
		if oargs:
			#args.append( '[%s]' % ','.join(oargs) )
			#args.append( '{%s}' % ','.join(oargs) )
			args.append( '__kwargs _kwargs_type_')
			node._arg_names.append( '__kwargs' )

		starargs = None
		if node.args.vararg:
			starargs = node.args.vararg
			assert starargs in args_typedefs
			args.append( '__vargs__ ...%s' %args_typedefs[starargs])
			node._arg_names.append( starargs )

		node._args_signature = ','.join(args)

		####
		if is_method:
			assert self._class_stack
			method = '(self *%s)  ' %self._class_stack[-1].name
		else:
			method = ''
		out = []
		if is_closure:
			if return_type:
				out.append( '%s := func (%s) %s {\n' % (node.name, ', '.join(args), return_type) )
			else:
				out.append( '%s := func (%s) {\n' % (node.name, ', '.join(args)) )
		else:
			if return_type:
				out.append( 'func %s%s(%s) %s {\n' % (method, node.name, ', '.join(args), return_type) )
			else:
				out.append( 'func %s%s(%s) {\n' % (method, node.name, ', '.join(args)) )
		self.push()

		if oargs:
			for n,v in oargs:
				out.append(self.indent() + '%s := %s' %(n,v))
				out.append(self.indent() + 'if __kwargs.__use__%s { %s = __kwargs.%s }' %(n,n,n))

		if starargs:
			out.append(self.indent() + '%s := &__vargs__' %starargs)

		if use_generics and generics:
			gname = args_names[ args_names.index(args_generics.keys()[0]) ]

			#panic: runtime error: invalid memory address or nil pointer dereference
			#[signal 0xb code=0x1 addr=0x0 pc=0x402440]
			##out.append(self.indent() + '__type__ := __gen__.(object).getclassname()')


			out.append(self.indent() + '__type__ := "INVALID"')
			out.append(self.indent() + '__super__, __ok__ := __gen__.(object)')

			#out.append(self.indent() + '__type__ = __super__.getclassname();')        ## TODO FIX ME
			#out.append(self.indent() + 'fmt.Println(__type__); ')
			#out.append(self.indent() + 'if __type__=="" { fmt.Println(__gen__.(object).__class__); }')

			out.append(self.indent() + 'if __ok__ { __type__ = __super__.getclassname();')
			out.append(self.indent() + '} else { fmt.Println("Gython RuntimeError - struct must implement the `object` interface"); }')

			out.append(self.indent() + 'switch __type__ {')
			#out.append(self.indent() + 'switch __gen__.(type) {')  ## this is not always correct
			#out.append('fmt.Println("class name: ", __type__)')

			self.push()
			gsorted = list(generics)
			gsorted.sort()
			gsorted.reverse()
			#for gt in generics:
			## this fails with a struct returned from a super method that returns self,
			## the generic function will fail with a nil struct, while it still works when passed the instance directly.
			for gt in gsorted:
				assert gt in self._classes
				#if node.name in self._classes[gt]._subclasses:
				#if len(self._classes[gt]._parents) == 0:

				## if in super class ##
				if self._class_stack and len(self._classes[self._class_stack[-1].name]._parents) == 0:
					if return_type=='*'+gt or not is_method: pass
					else: continue
				elif len(self._classes[gt]._parents) == 0: ## or if the generic is the super class skip it.
					if return_type=='*'+gt or not is_method: pass
					else: continue

				######out.append(self.indent() + 'case *%s:' %gt)
				out.append(self.indent() + 'case "%s":' %gt)
				self.push()

				#out.append(self.indent() + '%s,_ := __gen__.(*%s)' %(gname,gt) )  ## can not depend on the struct type, because subclasses are unions.
				out.append(self.indent() + '%s,__ok__ := __gen__.(*%s)' %(gname,gt) )  ## can not depend on the struct type, because subclasses are unions.

				out.append(self.indent() + 'if __ok__ {')

				for b in node.body:
					v = self.visit(b)
					if v:
						if returns_self:
							v = self._hack_return(v, return_type, gname, gt, node)
						out.append( self.indent() + v )

				out.append(self.indent() + '} else {' )
				if generic_base_class == gt or returns_self:
					out.append(' fmt.Println("Generics RuntimeError - generic argument is not a pointer to a struct", %s);' %gname)
					out.append(' fmt.Println("struct: ",__gen__);' )
				else:
					# __gen__.(C).foo();
					# this fails because the go compiler thinks that __gen__ is *B, when infact its *C
					# panic: interface conversion: interface is *main.B, not *main.C,
					# workaround: switch on type go thinks it is, and then recast to the real type.
					# s := C( *__gen__.(*B) )
					self.push()
					out.append( self.indent() + 'switch __gen__.(type) {' )
					self.push()
					for gt2 in gsorted:
						if gt2 != gt:
							out.append(self.indent() + 'case *%s:' %gt2)
							self.push()
							if gt2 == generic_base_class:
								## TODO panic here
								out.append(' fmt.Println("Generics RuntimeError - can not cast base class to a subclass type", %s);' %gname)
							else:
								out.append(self.indent() + '%s := %s( *__gen__.(*%s) )' %(gname, gt, gt2) )
								for b2 in node.body:
									v = self.visit(b2)
									if v:
										#if returns_self:
										#	v = self._hack_return(v, return_type, gname, gt, node)
										out.append( self.indent() + v )

							self.pull()

					self.pull()
					out.append(self.indent() + '}')
					self.pull()
				out.append(self.indent() + '}')
				self.pull()
			self.pull()
			out.append(self.indent() + '}')

			## this only helps with debugging when the generic function is expected to return something
			if return_type:
				out.append(self.indent() + 'fmt.Println("Generics RuntimeError - failed to convert type to:", __type__, __gen__)')

			if return_type == 'int':
				out.append(self.indent() + 'return 0')
			elif return_type == 'float':
				out.append(self.indent() + 'return 0.0')
			elif return_type == 'string':
				out.append(self.indent() + 'return ""')
			elif return_type == 'bool':
				out.append(self.indent() + 'return false')
			elif return_type:
				#raise NotImplementedError('TODO other generic function return types', return_type)
				out.append(self.indent() + 'return %s' %(return_type.replace('*','&')+'{}'))

		elif use_generics: ## no generics in args, generate generics caller switching
			body = node.body[:]
			body.reverse()
			self.generate_generic_branches( body, out, self._vars, self._known_vars )

		else: ## without generics ##
			for b in node.body:
				out.append(self.indent()+self.visit(b))

		self._scope_stack = []

		if is_method and return_type and node.name.endswith('__init__'):
			## note: this could be `__init__` or `ParentClass__init__`.
			has_return = False
			for ln in out:
				if ln.strip().startswith('return '):
					has_return = True
					break

			if not has_return:
				out.append('return self')

		self.pull()
		out.append( self.indent()+'}' )
		return '\n'.join(out)

	def _hack_return(self, v, return_type, gname, gt, node):
		## TODO - fix - this breaks easily
		if v.strip().startswith('return ') and '*'+gt != return_type:
			if gname in v and v.strip() != 'return self':
				if '(' not in v:
					v += '.(%s)' %return_type
					v = v.replace(gname, '__gen__')
					self.method_returns_multiple_subclasses[ self._class_stack[-1].name ].add(node.name)
		return v

	def generate_generic_branches(self, body, out, force_vars, force_used_vars):
		#out.append('/* GenerateGeneric */')
		#out.append('/*vars: %s*/' %self._vars)
		#out.append('/*used: %s*/' %self._known_vars)

		#force_vars, force_used_vars = self._scope_stack[-1]
		self._vars = set(force_vars)
		self._known_vars = set(force_used_vars)

		#out.append('/*force vars: %s*/' %force_vars)
		#out.append('/*force used: %s*/' %force_used_vars)

		prev_vars = None
		prev_used = None
		vars = None
		used = None

		vars = set(self._vars)
		used = set(self._known_vars)

		#out.append('/*Sstack len: %s*/' %len(self._scope_stack))
		#if self._scope_stack:
		#	out.append('/*stack: %s - %s*/' %self._scope_stack[-1])
		#	out.append('/*STAK: %s */' %self._scope_stack)


		while len(body):
			prev_vars = vars
			prev_used = used

			b = body.pop()
			try:
				v = self.visit(b)
				if v: out.append( self.indent() + v )
			except GenerateGenericSwitch as err:
				self._scope_stack.append( (set(self._vars), set(self._known_vars)))

				#out.append('/* 		GenerateGenericSwitch */')
				#out.append('/*	vars: %s*/' %self._vars)
				#out.append('/*	used: %s*/' %self._known_vars)
				#out.append('/*	prev vars: %s*/' %prev_vars)
				#out.append('/*	prev used: %s*/' %prev_used)
				#out.append('/*	stack: %s - %s*/' %self._scope_stack[-1])
				#out.append('/*	stack len: %s*/' %len(self._scope_stack))
				#out.append('/*	stack: %s*/' %self._scope_stack)

				G = err[0]
				if 'target' not in G:
					if isinstance(b, ast.Assign):
						G['target'] = self.visit(b.targets[0])
					else:
						raise SyntaxError('no target to generate generic switch')


				out.append(self.indent()+'__subclass__ := %s' %G['value'])
				out.append(self.indent()+'switch __subclass__.__class__ {')
				self.push()

				subclasses = self.get_subclasses( G['class'] )
				for sub in subclasses:
					#self._vars = prev_vars
					#self._known_vars = prev_used


					out.append(self.indent()+'case "%s":' %sub)
					self.push()
					#out.append(self.indent()+'%s := __subclass__.(*%s)' %(G['target'], sub)) ## error not an interface
					#out.append(self.indent()+'%s := %s(*__subclass__)' %(G['target'], sub))
					out.append(self.indent()+'__addr := %s(*__subclass__)' %sub)
					out.append(self.indent()+'%s := &__addr' %G['target'])

					pv, pu = self._scope_stack[-1]
					self.generate_generic_branches( body[:], out, pv, pu )

					self.pull()
				self._scope_stack.pop()

				self.pull()
				out.append(self.indent()+'}')
				return


	def _visit_call_helper_var(self, node):
		args = [ self.visit(a) for a in node.args ]
		if node.keywords:
			for key in node.keywords:
				args.append( key.arg )

		for name in args:
			if name not in self._vars:
				self._vars.add( name )

		return ''  ## do not declare variables in function head for Go backend


	def visit_Assign(self, node):
		if isinstance(node.targets[0], ast.Tuple):
			## special case for rust compatible style of creating sender,recver,
			## which in go are actually the same channel, below the go channel is assigned to both targets.
			if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name) and node.value.func.id=='__go_make_chan__':
				sender = self.visit(node.targets[0].elts[0])
				recver = self.visit(node.targets[0].elts[1])
				T = self.visit(node.value.args[0])
				return '%s := make(chan %s); %s := %s' %(sender, T, recver, sender)
			else:
				raise NotImplementedError('TODO')
		self._catch_assignment = False

		target = self.visit( node.targets[0] )


		if isinstance(node.value, ast.BinOp) and self.visit(node.value.op)=='<<' and isinstance(node.value.left, ast.Call) and node.value.left.func.id=='__go__map__':
			if isinstance(node.value.right, ast.Name) and node.value.right.id.startswith('__comp__'):
				value = self.visit(node.value.right)
				return '%s := %s;' % (target, value)  ## copy the map comprehension from the temp var to the original.

		################
		if isinstance(node.value, ast.BinOp) and self.visit(node.value.op)=='<<' and isinstance(node.value.left, ast.Name) and node.value.left.id=='__go__send__':
			value = self.visit(node.value.right)
			return '%s <- %s;' % (target, value)

		elif not self._function_stack:
			value = self.visit(node.value)
			#return 'var %s = %s;' % (target, value)
			if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name) and node.value.func.id in self._classes:
				#value = '__new__' + value
				return 'var %s *%s = %s;' % (target, node.value.func.id, value)
			else:
				return 'var %s = %s;' % (target, value)

		elif isinstance(node.targets[0], ast.Name) and node.targets[0].id in self._vars:
			value = self.visit(node.value)
			self._vars.remove( target )
			self._known_vars.add( target )

			if value.startswith('&[]*') and self._catch_assignment:
				self._known_arrays[ target ] = self._catch_assignment['class']


			if value.startswith('&(*') and '[' in value and ']' in value:  ## slice hack
				v = value[1:]
				self._slice_hack_id += 1
				return '__slice%s := %s; %s := &__slice%s;' %(self._slice_hack_id, v, target, self._slice_hack_id)

			elif isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute) and isinstance(node.value.func.value, ast.Name):
				varname = node.value.func.value.id
				if varname in self._known_vars:
					#raise SyntaxError(varname + ' is known class::' + self._known_instances[varname] + '%s(%s)' % (fname, args))
					cname = self._known_instances[varname]
					if node.value.func.attr in self.method_returns_multiple_subclasses[ cname ]:
						self._known_instances[target] = cname
						#raise SyntaxError('xxxxxxxxx %s - %s' % (self.visit(node.value), target ) )
						raise GenerateGenericSwitch( {'target':target, 'value':value, 'class':cname, 'method':node.value.func.attr} )
				return '%s := %s;' % (target, value)


			elif isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name):
				if node.value.func.id in self._classes:
					#raise SyntaxError(value+' in classes')
					self._known_instances[ target ] = node.value.func.id

				return '%s := %s;' % (target, value)

			else:
				return '%s := %s;' % (target, value)

		else:
			value = self.visit(node.value)
			#if '<-' in value:
			#	raise RuntimeError(target+value)
			if value.startswith('&make('):
				#raise SyntaxError(value)
				v = value[1:]
				return '_tmp := %s; %s = &_tmp;' %(v, target)
			else:
				#if value.startswith('&[]*') and self._catch_assignment:
				#	raise SyntaxError(value)
				return '%s = %s;' % (target, value)

	def visit_While(self, node):
		cond = self.visit(node.test)
		if cond == 'true' or cond == '1': cond = ''
		body = [ 'for %s {' %cond]
		self.push()
		for line in list( map(self.visit, node.body) ):
			body.append( self.indent()+line )
		self.pull()
		body.append( self.indent() + '}' )
		return '\n'.join( body )

	def _inline_code_helper(self, s):
		return s


def translate_to_go(script, insert_runtime=True):
	if '--debug-inter' in sys.argv:
		raise RuntimeError(script)
	if insert_runtime:
		runtime = open( os.path.join(RUSTHON_LIB_ROOT, 'src/runtime/go_builtins.py') ).read()
		script = runtime + '\n' + script

	try:
		tree = ast.parse(script)
	except SyntaxError as err:
		sys.stderr.write(script)
		raise err

	g = GoGenerator( source=script )
	g.visit(tree) # first pass gathers classes
	pass2 = g.visit(tree)


	## linux package: apt-get install golang
	exe = '/usr/bin/go'
	if not os.path.isfile(exe):
		## default path on linux from the offical Go docs - installed with their installer ##
		exe = '/usr/local/go/bin/go'  
		if not os.path.isfile(exe):
			exe = os.path.expanduser('~/go/bin/go')  ## fall back to user home directory
			if not os.path.isfile(exe):
				print 'WARNING: could not find go compiler'
				print 'only a single translation pass was performed'
				print '(the generated code may not compile)'
				return pass2

	## this hack runs the code generated in the second pass into the Go compiler to check for errors,
	## where an interface could not be type asserted, because Go found that the variable was not an interface,
	## parsing the errors from `go build` and matching the magic ids, in self.unodes on the node is set
	## `is_struct_pointer`, this triggers different code to be generated in the 3rd pass.
	## the Gython translator also has the same type information as Go, but it is simpler to use this hack.
	import subprocess
	pass2lines = pass2.splitlines()
	path = tempfile.gettempdir() + '/pass2.go'
	open(path, 'wb').write( pass2 )
	p = subprocess.Popen([exe, 'build', path], cwd=tempfile.gettempdir(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	errors = p.stderr.read().splitlines()
	if len(errors):
		for line in errors:
			if 'invalid type assertion' in line:
				if 'non-interface type' in line:
					lineno = int( line.split(':')[1] )
					src = pass2lines[ lineno-1 ]
					assert '__magic__' in src
					id = src.strip().split()[0]
					g.unodes[id].is_struct_pointer = True
				else:
					raise SyntaxError(line)

	return g.visit(tree) ## pass3


```
