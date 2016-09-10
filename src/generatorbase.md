Transpiler Base Class
---------------------
shared methods used by most backends are here.
TODO move `__init__` from jstranslator.md to here.

Imports
-------
* [@import clikelang.md](clikelang.md)

```python

class GeneratorBase( CLikeLanguage ):

	def visit_IfExp(self, node):
		## ternary operator ##
		test    = self.visit(node.test)
		iftrue  = self.visit(node.body)
		iffalse = self.visit(node.orelse)
		return '(%s ? %s : %s)' %(test, iftrue, iffalse)


	def visit_Expr(self, node):
		## note: the javascript backend overloads this ##
		s = self.visit(node.value)
		if s is None:
			raise RuntimeError('GeneratorBase ExpressionError: %s' %node.value)
		if s.strip() and not s.endswith(';'):
			s += ';'
		if s==';': return ''
		else: return s

	def function_has_getter_or_setter(self, node):
		options = {'getter':False, 'setter':False}
		for d in node.decorator_list:
			self._visit_decorator(d, options=options)
		return options['getter'] or options['setter']


	def visit_Tuple(self, node):
		if self._rust:
			return 'vec!(%s)' % ', '.join(map(self.visit, node.elts))
		elif self._cpp:
			return '{%s}' %','.join(map(self.visit, node.elts))
		else:
			return '[%s]' % ', '.join(map(self.visit, node.elts))

	def visit_List(self, node):
		a = []
		for elt in node.elts:
			b = self.visit(elt)
			if b is None: raise SyntaxError(elt)
			a.append( b )
		return '[%s]' % ', '.join(a)

	def visit_Subscript(self, node):
		if isinstance(node.slice, ast.Ellipsis):
			return self._visit_subscript_ellipsis( node )
		else:
			return '%s[%s]' % (self.visit(node.value), self.visit(node.slice))

	def visit_Index(self, node):
		return self.visit(node.value)

	def _visit_call_helper_instanceof(self, node):
		args = map(self.visit, node.args)
		if len(args) == 2:
			return '%s instanceof %s' %tuple(args)
		else:
			raise SyntaxError( args )

	def _visit_call_helper_new(self, node):
		args = map(self.visit, node.args)
		if len(args) == 1:
			return ' new %s' %args[0]
		else:
			raise SyntaxError( args )

	def _visit_call_special( self, node ):
		raise NotImplementedError('special call')

```
Call Function/Method
--------------------

The backends subclass _visit_call_helper, which gets called here after doing some bookeeping like
tracking what function names have been called, so backends can check `self._called_funtions` and
do extra things like inline extra helper code for things like `hasattr`, etc.

```python

	def visit_Call(self, node):
		name = self.visit(node.func)
		if name not in self._called_functions:
			self._called_functions[name] = 0
		self._called_functions[name] += 1

		if name in typedpython.GO_SPECIAL_CALLS.values():
			return self._visit_call_helper_go( node )

		elif name in self.catch_call:
			return self._visit_call_special( node )

		elif name == 'instanceof':  ## it is safer to use the builtin `isinstance`
			return self._visit_call_helper_instanceof( node )

		elif name == 'new':
			return self._visit_call_helper_new( node )

		elif name == '__ternary_operator__':
			args = map(self.visit, node.args)
			if len(args) == 2:
				return '((%s) ? %s : %s)' %(args[0], args[0], args[1])
			elif len(args) == 3:
				return '((%s) ? %s : %s)' %(args[0], args[1], args[2])
			else:
				raise SyntaxError( args )

		elif name == 'numpy.array':
			return self._visit_call_helper_numpy_array(node)

		elif name == 'JSObject':
			return self._visit_call_helper_JSObject( node )

		elif name == 'var':
			return self._visit_call_helper_var( node )

		elif name == 'JSArray':
			return self._visit_call_helper_JSArray( node )

		elif name == 'inline' or name == 'JS':
			assert len(node.args)==1 and isinstance(node.args[0], ast.Str)
			return self._inline_code_helper( node.args[0].s )

		elif name == 'list':
			return self._visit_call_helper_list( node )

		elif name == '__get__' and len(node.args)==2 and isinstance(node.args[1], ast.Str) and node.args[1].s=='__call__':
			raise SyntaxError('deprecated')
			return self._visit_call_helper_get_call_special( node )

		elif name.split('.')[-1] == '__go__receive__':
			raise SyntaxError('this should not happen __go__receive__')

		else:
			return self._visit_call_helper(node)



```

Import `import x` and `from x import y`
--------------------------------------

```python

	def _importfrom_helper(self, node):
		return ''

	def visit_ImportFrom(self, node):
		# print node.module
		# print node.names[0].name
		# print node.level
		if self._rust:
			crate = self._crates[node.module]
			for alias in node.names:
				crate.add( alias.name )
		if node.module=='runtime':
			self._insert_runtime = True
		else:
			return self._importfrom_helper(node)

		return ''

	def visit_Import(self, node):
		r = [alias.name.replace('__SLASH__', '/') for alias in node.names]
		res = []
		if r:
			for name in r:
				if self._rust:  ## TODO move this to rusttranslator.md
					if name not in self._crates:
						self._crates[name] = set()
				else:
					raise SyntaxError('import not yet support for this backend')

		if res:
			return '\n'.join(res)
		else:
			return ''

```


is_prim_type
------------
the typed backends like: go, rust and c++ need to know if a variable type is a builtin primitive,
or something that needs to be wrapped by a pointer/shared-reference.

```python

	def is_prim_type(self, T):
		prims = 'void bool int float double long string str char byte u32 u64 i32 i64 f32 f64 std::string cstring'.split()
		if self._go:
			prims.append( 'interface{}' )
		if T in prims:
			return True
		else:
			return False

	def indent(self): return '\t' * self._indent
	def push(self): self._indent += 1
	def pull(self):
		if self._indent > 0: self._indent -= 1

```



Function Decorators
-------------------
`_visit_decorator` is called by the other backends, the shared decorator logic is here.


```python

	def _visit_decorator(self, decor, node=None, options=None, args_typedefs=None, chan_args_typedefs=None, generics=None, args_generics=None, func_pointers=None, arrays=None ):
		assert node
		if options is None: options = dict()
		if args_typedefs is None: args_typedefs = dict()
		if chan_args_typedefs is None: chan_args_typedefs = dict()
		if generics is None: generics = set()
		if args_generics is None: args_generics = dict()
		if func_pointers is None: func_pointers = set()
		if arrays is None: arrays = dict()

		if isinstance(decor, ast.Name) and decor.id == 'classmethod':
			options['classmethod'] = True

		elif isinstance(decor, ast.Name) and decor.id == 'property':
			## a function is marked as a getter with `@property`
			options['getter'] = True
		elif isinstance(decor, ast.Attribute) and isinstance(decor.value, ast.Name) and decor.attr == 'setter':
			## a function is marked as a setter with `@name.setter`
			options['setter'] = True

		elif isinstance(decor, ast.Call) and isinstance(decor.func, ast.Name) and decor.func.id == '__typedef__':
			if len(decor.args) == 3:
				vname = self.visit(decor.args[0])
				if isinstance(decor.args[1], ast.Str):
					vtype = decor.args[1].s
				else:
					vtype = self.visit(decor.args[1])
				vptr = decor.args[2].s

				## note: the space is required because it could be `mut` rust-keyword, or `struct` C type.
				args_typedefs[ vname ] = '%s %s' %(vptr, vtype)

			else:
				for key in decor.keywords:
					if isinstance( key.value, ast.Str):
						args_typedefs[ key.arg ] = key.value.s
					elif isinstance(key.value, ast.Name):
						T = key.value.id
						if self.is_prim_type(T):
							args_typedefs[key.arg] = T
						elif self._cpp:
							if self.usertypes and 'shared' in self.usertypes:
								args_typedefs[ key.arg ] = self.usertypes['shared']['template'] %T
							elif not self._shared_pointers:
								args_typedefs[ key.arg ] = '%s*' %T
							elif self._unique_ptr:
								args_typedefs[ key.arg ] = 'std::unique_ptr<%s>' %T
							else:
								args_typedefs[ key.arg ] = 'std::shared_ptr<%s>' %T

						else:  ## javascript runtime checked types
							args_typedefs[key.arg] = T

					else:
						if isinstance(key.value, ast.Call) and isinstance(key.value.func, ast.Name) and key.value.func.id=='__arg_array__':
							arrays[ key.arg ] = key.value.args[0].s
							dims = arrays[ key.arg ].count('[')
							arrtype = arrays[ key.arg ].split(']')[-1]

							if self._rust:
								if not self.is_prim_type(arrtype):
									arrtype = 'Rc<RefCell<%s>>' %arrtype
								
								args_typedefs[ key.arg ] = 'Rc<RefCell<Vec<%s>>>' %arrtype

							elif self._cpp:
								## non primitive types (objects and arrays) can be None, `[]MyClass( None, None)`
								## use a pointer or smart pointer. 
								if not self.is_prim_type(arrtype):
									if not self._shared_pointers:
										arrtype += '*'
									elif self.usertypes and 'shared' in self.usertypes:
										arrtype = self.usertypes['shared']['template'] % arrtype
									elif self._unique_ptr:
										arrtype = 'std::unique_ptr<%s>' %arrtype
									else:
										arrtype = 'std::shared_ptr<%s>' %arrtype


								T = []

								for i in range(dims):
									if not self._shared_pointers:
										T.append('std::vector<')
									elif self.usertypes and 'vector' in self.usertypes:
										sptr = self.usertypes['shared']['type']
										vptr = self.usertypes['vector']['template'].split("%s")[0]
										T.append('%s%s' %(sptr, vptr))									
									elif self._unique_ptr:
										T.append('std::unique_ptr<std::vector<')
									else:
										T.append('std::shared_ptr<std::vector<')
								T.append( arrtype )

								if self._shared_pointers or 'vector' in self.usertypes:
									for i in range(dims):
										T.append('>>')
								else:
									for i in range(dims):
										if i: T.append('*>')
										else: T.append('>')
									T.append('*')

								args_typedefs[ key.arg ] = ''.join(T)

							else:  ## javascript backend
								args_typedefs[ key.arg ] = key.value.args[0].s

						else:
							args_typedefs[ key.arg ] = self.visit(key.value)

					if args_typedefs[key.arg].startswith('func(') or args_typedefs[key.arg].startswith('lambda('):
						is_lambda_style = args_typedefs[key.arg].startswith('lambda(')
						func_pointers.add( key.arg )
						funcdef = args_typedefs[key.arg]
						## TODO - better parser
						hack = funcdef.replace(')', '(').split('(')
						lambda_args = []
						TODO_REPLACE_PIPE_HACK = '|'  ## note new syntax is space separated
						for larg in hack[1].strip().split(TODO_REPLACE_PIPE_HACK):
							if self.is_prim_type(larg):
								lambda_args.append(larg)
							elif not larg:
								lambda_args.append('void')
							else:
								lambda_args.append('std::shared_ptr<%s>'%larg)

						lambda_args = ','.join(lambda_args)
						lambda_return = hack[3].strip()
						if not lambda_return: lambda_return = 'void'
						if not self.is_prim_type(lambda_return):
							lambda_return = 'std::shared_ptr<%s>'%lambda_return

						if self._cpp:
							if is_lambda_style:
								if lambda_return:  ## c++11
									args_typedefs[ key.arg ] = 'std::function<%s(%s)>  %s' %(lambda_return, lambda_args, key.arg)
								else:
									args_typedefs[ key.arg ] = 'std::function<void(%s)>  %s' %(lambda_args, key.arg)

							else:  ## old C style function pointers
								if lambda_return:
									args_typedefs[ key.arg ] = '%s(*%s)(%s)' %(lambda_return, key.arg, lambda_args)
								else:
									args_typedefs[ key.arg ] = 'void(*%s)(%s)' %(key.arg, lambda_args)

						elif self._rust:
							if lambda_return:
								args_typedefs[ key.arg ] = '|%s|->%s' %(lambda_args, lambda_return)
							else:
								args_typedefs[ key.arg ] = '|%s|' %lambda_args

						elif self._dart:
							args_typedefs[ key.arg ] = 'var'

					## check for super classes - generics ##
					## this was originally for the Go backend, still used in the c++ or rust backends?
					if (self._go or self._cpp or self._rust) and args_typedefs[ key.arg ] in self._classes:
						classname = args_typedefs[ key.arg ]
						options['generic_base_class'] = classname

						if self._cpp:
							if not self._shared_pointers:
								args_typedefs[ key.arg ] = '%s*' %classname
							elif self.usertypes and 'shared' in self.usertypes:
								args_typedefs[ key.arg ] = self.usertypes['shared']['template'] % classname
							elif self._unique_ptr:
								args_typedefs[ key.arg ] = 'std::unique_ptr<%s>' %classname
							else:
								args_typedefs[ key.arg ] = 'std::shared_ptr<%s>' %classname
							args_generics[ key.arg ] = classname

							for subclass in self._classes[classname]._subclasses:
								generics.add( subclass )

						elif self._rust:
							args_typedefs[ key.arg ] = 'Rc<RefCell<%s>>' %classname

						elif self._go:  ## TODO test if this is still working in the Go backend
							if node.name=='__init__':
								## generics type switch is not possible in __init__ because
								## it is used to generate the type struct, where types are static.
								## as a workaround generics passed to init always become `interface{}`
								args_typedefs[ key.arg ] = 'interface{}'
								#self._class_stack[-1]._struct_def[ key.arg ] = 'interface{}'
							else:
								generics.add( classname ) # switch v.(type) for each
								generics = generics.union( self._classes[classname]._subclasses )  ## TODO
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
				options['returns'] = decor.args[0].id
			else:
				options['returns'] = decor.args[0].s

			if options['returns'].startswith('[]'):
				options['returns_array'] = True
				options['returns_array_dim'] = options['returns'].count('[]')
				options['returns_array_type'] = options['returns'].split(']')[-1]
				if self._cpp:
					if options['returns_array_type']=='string':
						options['returns_array_type'] = 'std::string'

					T = []
					for i in range(options['returns_array_dim']):
						if not self._shared_pointers:
							T.append('std::vector<')
						elif self._unique_ptr:
							T.append('std::unique_ptr<std::vector<')
						else:
							T.append('std::shared_ptr<std::vector<')

					T.append(options['returns_array_type'])

					if self._shared_pointers:
						for i in range(options['returns_array_dim']):
							T.append('>>')
					else:
						for i in range(options['returns_array_dim']):
							if i: T.append('*>')
							else: T.append('>')
						T.append('*')
					options['returns'] = ''.join(T)
				elif self._rust:
					raise SyntaxError('TODO return 2d array rust backend')
				else:
					raise SyntaxError('TODO return 2d array some backend')

			if options['returns'] == 'self':
				options['returns_self'] = True
				self.method_returns_multiple_subclasses[ self._class_stack[-1].name ].add(node.name)

				if self._go:
					options['returns'] = '*' + self._class_stack[-1].name  ## go hacked generics

```
Function
---------
calls `_visit_function` which is subclassed by other backends.

```python

	def visit_FunctionDef(self, node):
		self._function_stack.append( node )
		node._local_vars = set()
		buffer = self._visit_function( node )

		if node == self._function_stack[0]:  ## global function
			self._global_functions[ node.name ] = node

		self._function_stack.pop()
		return buffer

```


With
----

Special syntax that triggers different things depending on the backend.
Also implements extra syntax like `switch` and `select`.

```python

	def visit_With(self, node):
		r = []
		is_select = False
		is_switch = False
		is_match  = False
		is_case   = False
		is_extern = False
		has_default = False

		if isinstance(node.context_expr, ast.Name) and node.context_expr.id in ('oo', 'operator_overloading'):
			self._with_oo = True
			body = []
			for b in node.body: body.append(self.visit(b))
			self._with_oo = False
			return '\n'.join(body)

		elif isinstance( node.context_expr, ast.Name ) and node.context_expr.id == '__default__':
			has_default = True
			if self._rust and not self._cpp:
				r.append(self.indent()+'}, _ => {')
			else:
				r.append(self.indent()+'default:')

		elif isinstance( node.context_expr, ast.Name ) and node.context_expr.id == '__select__':
			is_select = True
			self._match_stack.append( list() )
			self._in_select_hack = True

			if self._rust:
				r.append(self.indent()+'select! (')
			elif self._cpp:
				r.append(self.indent()+'cpp::select _select_;')  ## TODO nested, _select_N
			elif self._go:
				r.append(self.indent()+'select {')
			else:  ## javascript
				r.append('while (true) {		/* select loop */')


		elif isinstance( node.context_expr, ast.Call ):
			if not isinstance(node.context_expr.func, ast.Name):
				raise SyntaxError( self.visit(node.context_expr))

			#if len(node.context_expr.args):  ## what was this used for?
			#	a = self.visit(node.context_expr.args[0])
			#else:
			#	assert len(node.context_expr.keywords)
			#	## need to catch if this is a new variable ##
			#	name = node.context_expr.keywords[0].arg
			#	if name not in self._known_vars:
			#		a = 'let %s = %s' %(name, self.visit(node.context_expr.keywords[0].value))
			#	else:
			#		a = '%s = %s' %(name, self.visit(node.context_expr.keywords[0].value))

			if node.context_expr.func.id == '__case__':
				is_case = True
				case_match = None
				select_hack = None
				if not len(node.context_expr.args):
					assert len(node.context_expr.keywords)==1
					kw = node.context_expr.keywords[0]
					if self._go:
						case_match = '%s := %s' %(kw.arg, self.visit(kw.value))
					elif hasattr(self, '_in_select_hack') and self._in_select_hack:
						select_hack = True
						if self._cpp:
							case_match = '_select_.recv(%s, %s);' %(self.visit(kw.value), kw.arg)						

						else:  ## javascript backend ##
							#self.visit(kw.value) ## TODO allow worker returned from some call
							cid = kw.value.right.id
							case_match = 'if (𝑾𝒐𝒓𝒌𝒆𝒓𝑷𝒐𝒐𝒍.select(%s).length) {var %s = 𝑾𝒐𝒓𝒌𝒆𝒓𝑷𝒐𝒐𝒍.select(%s).pop();' %(cid, kw.arg, cid)

					else:
						case_match = '%s = %s' %(kw.arg, self.visit(kw.value))
				else:
					if isinstance(node.context_expr.args[0], ast.Compare):
						raise SyntaxError('"case x==n:" is not allowed in a case statement, use "case n:" instead.')
					case_match = self.visit(node.context_expr.args[0])

				if select_hack:
					r.append(self.indent()+case_match)
				elif self._rust and not self._cpp:
					if len(self._match_stack[-1])==0:
						r.append(self.indent()+'%s => {' %case_match)
					else:
						r.append(self.indent()+'}, %s => { ' %case_match )
				else:
					r.append(self.indent()+'case %s: {' %case_match) ## extra scope

				if not len(self._match_stack):
					raise SyntaxError('case statement used outside of a select or switch block')

				self._match_stack[-1].append(case_match)


			elif node.context_expr.func.id == '__switch__':
				is_switch = True
				self._match_stack.append( list() )

				if self._rust and not self._cpp:
					r.append(self.indent()+'match (%s) {' %self.visit(node.context_expr.args[0]))
					is_match = True
				else:
					r.append(self.indent()+'switch (%s) {' %self.visit(node.context_expr.args[0]))


			elif node.context_expr.func.id == 'extern':
				is_extern = True
				link = None
				for kw in node.context_expr.keywords:
					if kw.arg=='link':
						link = kw.value.s
				if self._cpp:
					r.append('extern "C" {')  ## TODO other abis
				elif self._rust:
					assert link
					r.append('#[link(name = "%s")]' %link)
					r.append('extern {')

				else:
					raise SyntaxError('with extern: not supported yet for backend')

				## strip the bodies from function defs, that should be just defined as `def f(args):pass`
				for b in node.body:
					if isinstance(b, ast.FunctionDef):
						if b.body and len(b.body) <= 2 and isinstance(b.body[-1], ast.Pass):
							b.body = []
							b.declare_only = True

			elif node.context_expr.func.id == 'syntax':
				assert len(node.context_expr.args)==1
				keys = []
				if isinstance(node.context_expr.args[0], ast.Dict):
					#self.usertypes = {'string':None}  ## force plain strings
					cfg = eval(self.visit(node.context_expr.args[0]))
					keys.extend( cfg.keys() )
					self.usertypes.update( cfg )
				else:
					assert isinstance(node.context_expr.args[0], ast.Str)
					jsonfile = node.context_expr.args[0].s
					if jsonfile in self.cached_json_files:
						jdata = self.cached_json_files[jsonfile]
						cfg   = json.loads( jdata )
						keys.extend( cfg.keys() )
						self.usertypes.update( cfg )
					elif os.path.isfile(jsonfile):
						cfg   = json.load(jsonfile)
						keys.extend( cfg.keys() )
						self.usertypes.update( cfg )
					else:
						raise RuntimeError('can not load custom types json: %s' %jsonfile)

				r = []
				for b in node.body:
					a = self.visit(b)
					if a: r.append(self.indent()+a)

				#self.usertypes = None  ## restore default types
				for k in keys:
					if k in self.usertypes:
						self.usertypes.pop(k)

				return '\n'.join(r)

			elif node.context_expr.func.id == 'timeout':
				assert len(node.context_expr.args)==1
				self._timeout = self.visit(node.context_expr.args[0])

				r = [
					'var __clk__ = (new Date()).getTime();',
					'while (true) {		/* timeout: %s */' %self._timeout,
				]
				self._in_timeout = True
				for b in node.body:
					a = self.visit(b)
					if a:
						r.append(self.indent()+a)
						if b is node.body[-1]:
							break
						if '(' in a and ')' in a:
							r.append(
								self.indent()+'if ( (new Date()).getTime() - __clk__ >= %s )  { break;}' % self._timeout
							)
				r.append('break; }')
				self._in_timeout = False
				return '\n'.join(r)


			else:
				raise SyntaxError( 'invalid use of with: %s' %node.context_expr)

		elif isinstance(node.context_expr, ast.Str):
			if self._cpp:
				body = ['namespace %s {' %node.context_expr.s]
				self.push()
				for b in node.body:
					body.append(self.visit(b))
				self.pull()
				body.append('}')
				return  '\n'.join(body)

			else:
				raise RuntimeError('TODO namespace for some backend')

		elif isinstance(node.context_expr, ast.Name) and node.optional_vars:
			assert isinstance(node.optional_vars, ast.Subscript)
			assert isinstance(node.optional_vars.slice, ast.Index)
			assert node.optional_vars.slice.value.id == 'MACRO'
			assert isinstance(node.optional_vars.value, ast.Str)
			if self._cpp:
				macro_string = self.visit_Str(node.optional_vars.value, wrap=False)
			else:
				macro_string = self.visit(node.optional_vars.value)[1:-1]

			macro_string = macro_string.replace('\\"', '"')

			if macro_string.startswith('"'):
				raise SyntaxError('bad macro: ' + macro_string)

			macro_name   = self.visit(node.context_expr)
			self.macros[ macro_name ] = macro_string  ## set macro
			r = []
			for b in node.body:
				a = self.visit(b)
				if a:
					if len(r): r.append(self.indent()+a)
					else: r.append(a)

			self.macros.pop( macro_name )  ## remove macro
			return '\n'.join(r)

		elif isinstance(node.context_expr, ast.Name):
			if node.context_expr.id == 'pointers':
				self._shared_pointers = False
				r = []
				for b in node.body:
					a = self.visit(b)
					if a: r.append(self.indent()+a)
				self._shared_pointers = True
				return '\n'.join(r)
			elif node.context_expr.id == 'gil':
				r = ['auto __gstate__ = PyGILState_Ensure();']
				for b in node.body:
					a = self.visit(b)
					if a: r.append(self.indent()+a)
				r.append('PyGILState_Release(__gstate__);')
				return '\n'.join(r)

			else:
				raise RuntimeError('TODO with syntax:%s'%node.context_expr.id)

		elif isinstance(node.context_expr, ast.Tuple) or isinstance(node.context_expr, ast.List):
			for elt in node.context_expr.elts:
				if elt.id == 'pointers':
					self._shared_pointers = False
				elif elt.id == 'noexcept':
					self._noexcept = True

			r = []
			for b in node.body:
				a = self.visit(b)
				if a: r.append(self.indent()+a)

			for elt in node.context_expr.elts:
				if elt.id == 'pointers':
					self._shared_pointers = True
				elif elt.id == 'noexcept':
					self._noexcept = False

			return '\n'.join(r)

		else:
			raise SyntaxError( 'invalid use of with', node.context_expr)


		for b in node.body:
			a = self.visit(b)
			if a: r.append(self.indent()+a)

		if is_case and not self._rust:  ## always break after each case - do not fallthru to default: block
			if select_hack or self._go:
				r.append(self.indent()+' break;}')
			else:
				r.append(self.indent()+'} break;')  ## } extra scope
		###################################

		if is_extern:
			r.append(self.indent()+'}')

		elif is_select:
			if self._cpp:
				r.append(self.indent()+'_select_.wait();')
			elif self._rust:
				r.append(self.indent()+'})')  ## rust needs extra closing brace for the match-block
			elif self._go:
				r.append(self.indent()+'}')
			else:
				r.append(self.indent()+'break; }')

		elif is_switch:
			if self._rust and not self._cpp:
				r.append(self.indent()+'}}')  ## rust needs extra closing brace for the match-block
			else:
				r.append(self.indent()+'}')

		return '\n'.join(r)

```

Go hacks
--------
TODO clean up.

```python

	def parse_go_style_arg( self, s ):
		if isinstance(s, ast.Str): s = s.s
		return s.split(']')[-1]

	def _visit_call_helper_go(self, node):
		go_types = 'bool string int float64'.split()

		name = self.visit(node.func)
		if name == '__go__':
			if self._cpp:
				## simple auto threads
				thread = '__thread%s__' %len(self._threads)
				self._threads.append(thread)
				closure_wrapper = '[&]{%s;}'%self.visit(node.args[0])
				return 'std::thread %s( %s );' %(thread, closure_wrapper)
			elif self._rust:
				return 'thread::spawn( move || {%s;} );' % self.visit(node.args[0])
			elif self._go:
				return 'go %s' %self.visit(node.args[0])
			else:  ## javascript
				r = self.visit(node.args[0])
				mode = 'call'
				fname = self.visit(node.args[0].func)
				args = [self.visit(a) for a in node.args[0].args]
				if fname == 'new':
					mode = 'new'
					fname = self.visit(node.args[0].args[0].func)
					args = [self.visit(a) for a in node.args[0].args[0].args]
				if node.keywords:
					if not node.keywords[0].arg=='cpu':
						raise SyntaxError('invalid keyword argument to the builtin `spawn`')
					cpuid = self.visit(node.keywords[0].value)
					return 'ⲢⲑⲑⲒ.spawn({%s:"%s", args:[%s]}, {cpu:%s})' %(mode,fname, ','.join(args), cpuid)
				else:
					return 'ⲢⲑⲑⲒ.spawn({%s:"%s", args:[%s]})' %(mode,fname, ','.join(args))

		elif name == '__go_make__':
			if len(node.args)==2:
				return 'make(%s, %s)' %(self.visit(node.args[0]), self.visit(node.args[1]))
			elif len(node.args)==3:
				return 'make(%s, %s, %s)' %(self.visit(node.args[0]), self.visit(node.args[1]), self.visit(node.args[1]))
			else:
				raise SyntaxError('go make requires 2 or 3 arguments')
		elif name == '__go_make_chan__':
			## channel constructors
			if self._cpp:
				## cpp-channel API supports input/output
				T = self.visit(node.args[0])
				if self.is_prim_type(T):
					return 'cpp::channel<%s>{}'%T
				else:
					return 'cpp::channel<%s*>{}'%T
			elif self._rust:
				## rust returns a tuple input/output that needs to be destructured by the caller
				return 'channel::<%s>()' %self.visit(node.args[0])
			else:  ## Go
				return 'make(chan %s)' %self.visit(node.args[0])

		elif name == '__go__array__':
			if isinstance(node.args[0], ast.BinOp):# and node.args[0].op == '<<':  ## todo assert right is `typedef`
				a = self.visit(node.args[0].left)
				if a in go_types:
					if self._go:
						return '*[]%s' %a
					elif self._rust:
						return '&mut Vec<%s>' %a  ## TODO test this
					else:
						raise RuntimeError('todo')
				else:
					return '*[]*%s' %a  ## todo - self._catch_assignment_array_of_obs = true

			else:
				a = self.visit(node.args[0])
				if a in go_types:
					return '[]%s{}' %a
				else:
					return '[]*%s{}' %a
		elif name == '__go__addr__':
			return '&%s' %self.visit(node.args[0])
		else:
			raise SyntaxError(name)

```