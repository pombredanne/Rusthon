Python to Intermediate Form
---------------------------

by Amirouche Boubekki and Brett Hartshorn - copyright 2013
License: "New BSD"

* [@import fakestdlib.md](fakestdlib.md)

```python


import os, sys, copy
from types import GeneratorType

import ast
from ast import Str
from ast import Call
from ast import Name
from ast import Tuple
from ast import Assign
from ast import keyword
from ast import Subscript
from ast import Attribute
from ast import FunctionDef
from ast import BinOp
from ast import Pass
from ast import Global
from ast import With

from ast import parse
from ast import NodeVisitor



POWER_OF_TWO = [ 2**i for i in range(32) ]

writer = writer_main = CodeWriter()

__webworker_writers = dict()
def get_webworker_writer( jsfile ):
	if jsfile not in __webworker_writers:
		__webworker_writers[ jsfile ] = CodeWriter()
	return __webworker_writers[ jsfile ]



class Typedef(object):
	# http://docs.python.org/2/reference/datamodel.html#emulating-numeric-types
	_opmap = dict(
		__add__ = '+',
		__iadd__ = '+=',
		__sub__ = '-',
		__isub__ = '-=',
		__mul__ = '*',
		__imul__ = '*=',
		__div__ = '/',
		__idiv__ = '/=',
		__mod__ = '%',
		__imod__ = '%=',
		__lshift__ = '<<',
		__ilshift__ = '<<=',
		__rshift__ = '>>',
		__irshift__ = '>>=',
		__and__ = '&',
		__iand__ = '&=',
		__xor__ = '^',
		__ixor__ = '^=',
		__or__ = '|',
		__ior__ = '|=',
	)

	def __init__(self, **kwargs):
		for name in kwargs.keys():  ## name, methods, properties, attributes, class_attributes, parents
			setattr( self, name, kwargs[name] )

		self.operators = dict()
		for name in self.methods:
			if name in self._opmap:
				op = self._opmap[ name ]
				self.operators[ op ] = self.get_pythonjs_function_name( name )

	def get_pythonjs_function_name(self, name):
		assert name in self.methods
		return '__%s_%s' %(self.name, name) ## class name

	def check_for_parent_with(self, method=None, property=None, operator=None, class_attribute=None):

		for parent_name in self.parents:
			if not self.compiler.is_known_class_name( parent_name ):
				continue

			typedef = self.compiler.get_typedef( class_name=parent_name )
			if method and method in typedef.methods:
				return typedef
			elif property and property in typedef.properties:
				return typedef
			elif operator and typedef.operators:
				return typedef
			elif class_attribute in typedef.class_attributes:
				return typedef
			elif typedef.parents:
				res = typedef.check_for_parent_with(
					method=method, 
					property=property, 
					operator=operator,
					class_attribute=class_attribute
				)
				if res:
					return res




class PythonToPythonJS(NodeVisitorBase):

	identifier = 0  ## clean up
	_func_typedefs = ()  ## TODO clean up

	def __init__(self, source=None, modules=False, module_path=None, dart=False, coffee=False, go=False, rust=False, cpp=False, fast_javascript=False, pure_javascript=False):
		#super(PythonToPythonJS, self).__init__()
		NodeVisitorBase.__init__(self, source)  ## note self._source gets changed below

		## lowlevel is code within a `with lowlevel:` block
		## this is used to define some builtin methods for each backend,
		## where the user wants the most direct translation possible to
		## the target backend.  This is only for special cases.
		self._with_ll = False   ## lowlevel

		self._modules = modules          ## split into mutiple files by class
		self._module_path = module_path  ## used for user `from xxx import *` to load .py files in the same directory.
		self._with_coffee = coffee
		self._with_dart = dart
		self._with_go = go
		self._with_gojs = False
		self._with_rust = rust
		self._with_cpp = cpp
		self._fast_js = fast_javascript
		self._strict_mode = pure_javascript

		## TODO _with_js should be renamed to _with_restricted_python, or _with_rpy.
		## originally this option was only used to switch modes from the original
		## full python mode to the faster more restricted python mode.
		## The older full python mode requires a backend that is very dynamic, like: javascript or lua
		## full python mode maps all calls through a generic `__get__` method that takes care of all
		## dynamic mapping at runtime, this basically emulates what CPython is doing in C in a slower VM.
		## full python mode also breaks down classes into flat function calls, for backends that do not
		## directly support classes like Lua and JavaScript.
		## The JavaScript backend now defaults to restricted python mode, because it is much faster,
		## and classes are now translated to JavaScript prototypes and constructed by calling new,
		## this also provides much better interop with external JS libraries.
		## Since restricted python mode became default the new backends: rust and c++ now require that mode,
		## and it makes the last stage of translation simpler and more generic.
		## However, the Lua backend still requires the old style full python mode, because in Lua classes
		## must be fully broken down into flat functions.
		self._with_js = True


		if self._with_rust or self._with_go:
			self._use_destructured_assignment = True
		else:
			self._use_destructured_assignment = False

		self._html_tail = []; script = False
		if source.strip().startswith('<html'):
			lines = source.splitlines()
			for line in lines:
				if line.strip().startswith('<script'):
					if 'type="text/python"' in line:
						writer.write( '<script type="text/python">')
						script = list()
					elif 'src=' in line and '~/' in line:  ## external javascripts installed in users home folder
						x = line.split('src="')[-1].split('"')[0]
						if os.path.isfile(os.path.expanduser(x)):
							o = []
							o.append( '<script type="text/javascript">' )
							if x.lower().endswith('.coffee'):
								import subprocess
								proc = subprocess.Popen(
									['coffee','--bare', '--print', os.path.expanduser(x)], 
									stdout=subprocess.PIPE
								)
								o.append( proc.stdout.read() )
							else:
								o.append( open(os.path.expanduser(x), 'rb').read() )
							o.append( '</script>')
							if script is True:
								self._html_tail.extend( o )
							else:
								for y in o:
									writer.write(y)

					else:
						writer.write(line)

				elif line.strip() == '</script>':
					if type(script) is list and len(script):
						source = '\n'.join(script)
						script = True
						self._html_tail.append( '</script>')
					else:
						writer.write( line )

				elif isinstance( script, list ):
					script.append( line )

				elif script is True:
					self._html_tail.append( line )

				else:
					writer.write( line )

		## preprocess the input source that may contain extended syntax
		## that the python AST parser can not deal with.
		## note: `transform_source` translates into an intermediate form
		## that is python AST compatible.
		source = typedpython.transform_source( source )


		## optimize "+" and "*" operator, for python syntax like 'a'*3 becomes 'aaa'
		if fast_javascript:
			self._direct_operators = set( ['+', '*'] )
		else:
			self._direct_operators = set()

		self._in_catch_exception = False
		self._in_lambda = False
		self._in_while_test = False
		self._use_threading = False
		self._use_sleep = False  ## only for the js backend, makes while loops `sleep` using setTimeOut
		self._use_array = False
		self._webworker_functions = dict()
		self._webworker_imports = list()
		self._with_webworker = False
		self._with_rpc = None
		self._with_rpc_name = None
		self._with_direct_keys = fast_javascript

		self._with_glsl = False  ## TODO dep

		self._source = source.splitlines()
		self._class_stack = list()
		self._classes = dict()    ## class name : [method names]
		self._class_parents = dict()  ## class name : parents
		self._instance_attributes = dict()  ## class name : [attribute names]
		self._class_attributes = dict()
		self._catch_attributes = None
		self._typedef_vars = dict()

		#self._names = set() ## not used?
		## inferred class instances, TODO regtests to confirm that this never breaks ##
		self._instances = dict()  ## instance name : class name

		self._decorator_properties = dict()
		self._decorator_class_props = dict()
		self._function_return_types = dict()
		self._return_type = None


		self._typedefs = dict()  ## class name : typedef  (deprecated - part of the old static type finder)

		self._globals = dict()
		self._global_nodes = dict()
		self._with_static_type = None
		self._global_typed_lists = dict()  ## global name : set  (if len(set)==1 then we know it is a typed list)
		self._global_typed_dicts = dict()
		self._global_typed_tuples = dict()
		self._global_functions = dict()
		self._autotyped_dicts  = dict()

		self._js_classes = dict()
		self._in_js_class = False
		self._in_assign_target = False
		self._with_runtime_exceptions = True  ## this is only used in full python mode.

		self._iter_ids = 0
		self._addop_ids = 0

		self._cache_while_body_calls = False
		self._comprehensions = []
		self._generator_functions = set()

		self._in_loop_with_else = False
		self._introspective_functions = False

		self._custom_operators = {}
		self._injector = []  ## advanced meta-programming hacks
		self._in_class = None
		self._with_fastdef = False
		self.setup_builtins()

		source = self.preprocess_custom_operators( source )

		tree = ast.parse( source )

		self._generator_function_nodes = collect_generator_functions( tree )

		for node in tree.body:
			## skip module level doc strings ##
			if isinstance(node, ast.Expr) and isinstance(node.value, ast.Str):
				pass
			else:
				self.visit(node)

		if self._html_tail:
			for line in self._html_tail:
				writer.write(line)

	def get_webworker_imports(self):
		return self._webworker_imports

	def has_webworkers(self):
		return len(self._webworker_functions.keys())

	def get_webworker_file_names(self):
		return set(self._webworker_functions.values())

	def preprocess_custom_operators(self, data):
		'''
		custom operators must be defined before they are used
		'''
		code = []
		for line in data.splitlines():
			if line.strip().startswith('@custom_operator'):
				l = line.replace('"', "'")
				a,b,c = l.split("'")
				op = b.decode('utf-8')
				self._custom_operators[ op ] = None
			else:
				for op in self._custom_operators:
					op = op.encode('utf-8')
					line = line.replace(op, '|"%s"|'%op)

			code.append( line )

		data = '\n'.join( code )
		return data

	def setup_builtins(self):
		self._classes['dict'] = set(['__getitem__', '__setitem__'])
		self._classes['list'] = set() #['__getitem__', '__setitem__'])
		self._classes['tuple'] = set() #['__getitem__', '__setitem__'])
		self._builtin_classes = set(['dict', 'list', 'tuple'])
		self._builtin_functions = {
			'ord':'%s.charCodeAt(0)',
			'chr':'String.fromCharCode(%s)',
			'abs':'Math.abs(%s)',
			'cos':'Math.cos(%s)',
			'sin':'Math.sin(%s)',
			'sqrt':'Math.sqrt(%s)'
		}
		self._builtin_functions_dart = {
			'ord':'%s.codeUnitAt(0)',
			'chr':'new(String.fromCharCode(%s))',
		}

	def is_known_class_name(self, name):
		return name in self._classes

	def get_typedef(self, instance=None, class_name=None):
		assert instance or class_name
		if isinstance(instance, Name) and instance.id in self._instances:
			class_name = self._instances[ instance.id ]

		if class_name:
			#assert class_name in self._classes
			if class_name not in self._classes:
				#raise RuntimeError('class name: %s - not found in self._classes - node:%s '%(class_name, instance))
				return None  ## TODO hook into self._typedef_vars

			if class_name not in self._typedefs:
				self._typedefs[ class_name ] = Typedef(
					name = class_name,
					methods = self._classes[ class_name ],
					#properties = self._decorator_class_props[ class_name ],
					#attributes = self._instance_attributes[ class_name ],
					#class_attributes = self._class_attributes[ class_name ],
					#parents = self._class_parents[ class_name ],
					properties = self._decorator_class_props.get(  class_name, set()),
					attributes = self._instance_attributes.get(    class_name, set()),
					class_attributes = self._class_attributes.get( class_name, set()),
					parents = self._class_parents.get(             class_name, set()),

					compiler = self,
				)
			return self._typedefs[ class_name ]

	def visit_Delete(self, node):
		writer.write('del %s' %','.join([self.visit(t) for t in node.targets]))

	def visit_Import(self, node):
		'''
		fallback to requirejs or if in webworker importScripts.
		some special modules from pythons stdlib can be faked here like:
			. threading

		nodejs only:
			. tornado
			. os

		'''

		tornado = ['tornado', 'tornado.web', 'tornado.ioloop']

		for alias in node.names:
			if self._with_go or self._with_rust or self._with_cpp:
				if alias.asname:
					writer.write('import %s as %s' %(alias.name, alias.asname))
				else:
					writer.write('import %s' %alias.name)
			elif self._with_webworker:
				self._webworker_imports.append( alias.name )
			elif alias.name in tornado:
				pass  ## pythonjs/fakelibs/tornado.py
			elif alias.name == 'tempfile':
				pass  ## pythonjs/fakelibs/tempfile.py
			elif alias.name == 'sys':
				pass  ## pythonjs/fakelibs/sys.py
			elif alias.name == 'subprocess':
				pass  ## pythonjs/fakelibs/subprocess.py
			elif alias.name == 'numpy':
				pass

			elif alias.name == 'json' or alias.name == 'os':
				pass  ## part of builtins.py
			elif alias.name == 'threading':
				self._use_threading = True
				#writer.write( 'Worker = require("/usr/local/lib/node_modules/workerjs")')

				## note: nodewebkit includes Worker, but only from the main script context,
				## there might be a bug in requirejs or nodewebkit where Worker gets lost
				## when code is loaded into main as a module using requirejs, as a workaround
				## allow "workerjs" to be loaded as a fallback, however this appears to not work in nodewebkit.
				writer.write( 'if __NODEJS__==True and typeof(Worker)=="undefined": Worker = require("workerjs")')

			#elif alias.asname:
			#	#writer.write( '''inline("var %s = requirejs('%s')")''' %(alias.asname, alias.name) )
			#	writer.write( '''inline("var %s = require('%s')")''' %(alias.asname, alias.name.replace('__DASH__', '-')) )
			#elif '.' in alias.name:
			#	raise NotImplementedError('import with dot not yet supported: line %s' % node.lineno)
			#else:
			#	#writer.write( '''inline("var %s = requirejs('%s')")''' %(alias.name, alias.name) )
			#	writer.write( '''inline("var %s = require('%s')")''' %(alias.name, alias.name) )

			elif alias.asname:
				writer.write('import %s as %s' %(alias.name, alias.asname))
			else:
				writer.write('import %s' %alias.name)


	def visit_ImportFrom(self, node):
		if self._with_go:
			lib = fakestdlib.GO
		elif self._with_cpp:
			lib = fakestdlib.CPP
		elif self._with_rust:
			lib = {}
		else:
			lib = fakestdlib.JS

		if self._module_path:
			path = os.path.join( self._module_path, node.module+'.py')
		else:
			path = os.path.join( './', node.module+'.py')

		if node.module == 'time' and node.names[0].name == 'sleep':
			if not (self._with_cpp or self._with_rust or self._with_go or self._with_ll):
				self._use_sleep = True

		############################################################
		if node.module == 'array' and node.names[0].name == 'array':
			self._use_array = True ## this is just a hint that calls to array call the builtin array

		elif node.module == 'bisect' and node.names[0].name == 'bisect':
			## bisect library is part of the stdlib,
			## in pythonjs it is a builtin function defined in builtins.py
			pass
		elif node.module == '__future__':
			pass

		elif node.module in lib:
			imported = False
			for n in node.names:
				if n.name in lib[ node.module ]:
					if not imported:
						imported = True
						if fakestdlib.REQUIRES in lib[node.module]:
							writer.write('import %s' %','.join(lib[node.module][fakestdlib.REQUIRES]))

					writer.write( 'inline("%s")' %lib[node.module][n.name] )
					if n.name not in self._builtin_functions:
						self._builtin_functions[ n.name ] = n.name + '()'

		elif os.path.isfile(path):
			## user import `from mymodule import *` TODO support files from other folders
			## this creates a sub-translator, because they share the same `writer` object (a global),
			## there is no need to call `writer.write` here.
			## note: the current pythonjs.configure mode here maybe different from the subcontext.
			data = open(path, 'rb').read()
			subtrans = PythonToPythonJS(
				data,
				module_path     = self._module_path,
				fast_javascript = self._fast_js,
				modules         = self._modules,
				pure_javascript = self._strict_mode,
			)
			self._js_classes.update( subtrans._js_classes ) ## TODO - what other typedef info needs to be copied here?

		elif self._with_rust:  ## allow `import xx` to be translated to `extern crate xx`
			writer.write('from %s import %s' %(node.module, ','.join([n.name for n in node.names])))
		elif node.module == 'runtime':
			writer.write('from runtime import *')
		elif node.module == 'nodejs':
			writer.write('from nodejs import *')
		elif node.module == 'nodejs.tornado':
			writer.write('from nodejs.tornado import *')
		elif self._with_js:
			inames = [n.name for n in node.names]
			writer.write('from %s import %s' %(node.module, ','.join(inames)))
		else:
			msg = 'invalid import - file not found: %s'%path
			raise SyntaxError( self.format_error(msg) )

	def visit_Assert(self, node):
		writer.write('assert %s' %self.visit(node.test))

	def visit_Set(self, node):  ## new python3 style `a={1,2,3}`
		return '{%s}' %','.join([self.visit(elt) for elt in node.elts])

	def visit_Dict(self, node):
		node.returns_type = 'dict'
		keytype = None
		a = []
		alt = []
		for i in range( len(node.keys) ):
			if isinstance(node.keys[i], ast.Num):
				if type(node.keys[i].n) is int:
					if keytype is None:
						keytype = 'int'
					elif keytype != 'int':
						raise SyntaxError(self.format_error('dictionary can not have mixed string and number keys'))
			elif isinstance(node.keys[i], ast.Str):
				if keytype is None:
					keytype = 'string'
				elif keytype != 'string':
					raise SyntaxError(self.format_error('dictionary can not have mixed string and number keys'))


			k = self.visit( node.keys[ i ] )
			v = node.values[i]


			if isinstance(v, ast.Lambda):
				v.keep_as_lambda = True
			v = self.visit( v )
			if self._with_ll or self._with_go or self._with_rust or self._with_cpp:
				a.append( '%s:%s'%(k,v) )
			elif self._fast_js:
				if not isinstance(node.keys[i], ast.Name):
					if isinstance(node.keys[i], ast.List):
						if len(node.keys[i].elts) != 1:
							raise SyntaxError(
								self.format_error('JavaScript ES6 Error: computed property name, `[]` wrapper not of length one.')
							)
						k = self.visit(node.keys[i].elts[0])
					alt.append( '[%s, %s]' %(k,v) )
				else:
					a.append( '%s:%s'%(k,v) )
			elif self._with_js:
				## TODO remove this
				a.append( '[%s,%s]'%(k,v) )
			else:
				raise RuntimeError( self.format_error('invalid backend') )


		if self._with_ll or self._with_go or self._with_rust or self._with_cpp:
			b = ','.join( a )
			return '{%s}' %b
		elif self._fast_js:
			b = ','.join( a )
			opts = '{copy:False,'
			if keytype is not None:
				opts += 'keytype:"%s",' %keytype
			if len(alt):
				opts += 'iterable:[%s]' %','.join(alt)
			opts += '}'
			return 'dict({%s}, %s )' %(b, opts)

		elif self._with_js:  ## DEPRECATED - note: this allowed for python style dict literals
			b = ','.join( a )
			return '__jsdict( [%s] )' %b
		else:
			raise RuntimeError('dict - unknown backend')

	def visit_Tuple(self, node):
		node.returns_type = 'tuple'
		#a = '[%s]' % ', '.join(map(self.visit, node.elts))
		a = []
		for e in node.elts:
			if isinstance(e, ast.Lambda):
				e.keep_as_lambda = True
			v = self.visit(e)
			assert v is not None
			a.append( v )

		if self._with_rust or self._with_cpp:
			if len(a)==1:
				return '(%s,)' % a[0]
			else:
				return '(%s)' % ', '.join(a)
		else:
			return '[%s]' % ', '.join(a)

	def visit_List(self, node):
		node.returns_type = 'list'

		a = []
		for e in node.elts:
			if isinstance(e, ast.Lambda):  ## inlined and called lambda "(lambda x: x)(y)"
				e.keep_as_lambda = True
			v = self.visit(e)
			assert v is not None
			a.append( v )

		return '[%s]' % ', '.join(a)

	def visit_GeneratorExp(self, node):
		return self.visit_ListComp(node)

	_comp_id = 0

	def visit_DictComp(self, node):
		'''
		node.key is key name
		node.value is value
		'''
		#raise SyntaxError(self.visit(node.key))  ## key, value, generators

		node.returns_type = 'dict'

		if len(self._comprehensions) == 0:
			comps = collect_dict_comprehensions( node )
			for i,cnode in enumerate(comps):
				cname = '__comp__%s' % self._comp_id
				cnode._comp_name = cname
				self._comprehensions.append( cnode )
				self._comp_id += 1


		cname = node._comp_name
		writer.write('var(%s)'%cname)

		length = len( node.generators )
		a = ['idx%s'%i for i in range(length)]
		writer.write('var( %s )' %','.join(a) )
		a = ['iter%s'%i for i in range(length)]
		writer.write('var( %s )' %','.join(a) )
		a = ['get%s'%i for i in range(length)]
		writer.write('var( %s )' %','.join(a) )

		if self._with_go:
			assert node.go_dictcomp_type
			k,v = node.go_dictcomp_type
			writer.write('%s = __go__map__(%s, %s)<<{}' %(cname, k,v))
		else:
			writer.write('%s = {}'%cname)

		generators = list( node.generators )
		generators.reverse()
		self._gen_comp( generators, node )

		self._comprehensions.remove( node )
		return cname


	def visit_ListComp(self, node):
		node.returns_type = 'list'
		if self._with_rust or self._with_cpp:
			## pass directly to next translation stage
			gen = node.generators[0]
			a = self.visit(node.elt)
			b = self.visit(gen.target)
			c = self.visit(gen.iter)
			return '[%s for %s in %s]' %(a,b,c)
		else:
			compname = self._visit_listcomp_helper(node)
			return compname

	def _visit_listcomp_helper(self, node):
		## TODO - move this logic to the next translation stage for each backend.
		## TODO - check if there was a bug here, why only when self._comprehensions is zero?
		#if len(self._comprehensions) == 0 or True:
		comps = collect_comprehensions( node )
		assert comps
		for i,cnode in enumerate(comps):
			cname = '__comp__%s' % self._comp_id
			cnode._comp_name = cname
			self._comprehensions.append( cnode )
			self._comp_id += 1

		cname = node._comp_name
		writer.write('var(%s)'%cname)
		#writer.write('var(__comp__%s)'%self._comp_id)

		length = len( node.generators ) + (len(self._comprehensions)-1)
		a = ['idx%s'%i for i in range(length)]
		writer.write('var( %s )' %','.join(a) )
		a = ['iter%s'%i for i in range(length)]
		writer.write('var( %s )' %','.join(a) )
		a = ['get%s'%i for i in range(length)]
		writer.write('var( %s )' %','.join(a) )

		if self._with_go:
			assert node.go_listcomp_type
			#writer.write('__comp__%s = __go__array__(%s)' %(self._comp_id, node.go_listcomp_type))
			writer.write('%s = __go__array__(%s)' %(cname, node.go_listcomp_type))
		else:
			writer.write('%s = JSArray()'%cname)

		generators = list( node.generators )
		generators.reverse()
		self._gen_comp( generators, node )

		#if node in self._comprehensions:
		#	self._comprehensions.remove( node )

		if self._with_go:
			#return '__go__addr__(__comp__%s)' %self._comp_id
			return '__go__addr__(%s)' %cname
		else:
			#return '__comp__%s' %self._comp_id
			return cname


	def _gen_comp(self, generators, node):
		#self._comp_id += 1
		#id = self._comp_id

		gen = generators.pop()
		id = len(generators) + self._comprehensions.index( node )
		assert isinstance(gen.target, Name)
		writer.write('idx%s = 0'%id)

		is_range = False
		if isinstance(gen.iter, ast.Call) and isinstance(gen.iter.func, ast.Name) and gen.iter.func.id in ('range', 'xrange'):
			is_range = True

			writer.write('iter%s = %s' %(id, self.visit(gen.iter.args[0])) )
			writer.write('while idx%s < iter%s:' %(id,id) )
			writer.push()

			writer.write('var(%s)'%gen.target.id)
			writer.write('%s=idx%s' %(gen.target.id, id) )

		elif self._with_js:  ## only works with arrays in javascript mode
			writer.write('iter%s = %s' %(id, self.visit(gen.iter)) )
			writer.write('while idx%s < iter%s.length:' %(id,id) )
			writer.push()
			writer.write('var(%s)'%gen.target.id)
			writer.write('%s=iter%s[idx%s]' %(gen.target.id, id,id) )

		else:
			raise SyntaxError('deprecated - lua backend')

		if generators:
			self._gen_comp( generators, node )
		else:
			cname = node._comp_name #self._comprehensions[-1]
			#cname = '__comp__%s' % self._comp_id

			if len(gen.ifs):
				test = []
				for compare in gen.ifs:
					test.append( self.visit(compare) )

				writer.write('if %s:' %' and '.join(test))
				writer.push()
				self._gen_comp_helper(cname, node)
				writer.pull()

			else:
				self._gen_comp_helper(cname, node)

		writer.write('idx%s+=1' %id )
		writer.pull()

	def _gen_comp_helper(self, cname, node):
		if isinstance(node, ast.DictComp):
			key = self.visit(node.key)
			val = self.visit(node.value)
			if self._with_go:
				writer.write('%s[ %s ] = %s' %(cname, key, val) )
			else:
				writer.write('%s[ %s ] = %s' %(cname, key, val) )

		elif self._with_go:
			writer.write('%s = append(%s, %s )' %(cname, cname,self.visit(node.elt)) )
		else:
			writer.write('%s.push( %s )' %(cname,self.visit(node.elt)) )

	def visit_In(self, node):
		return ' in '

	def visit_NotIn(self, node):
		#return ' not in '
		raise RuntimeError('"not in" is only allowed in if-test: see method - visit_Compare')

	## TODO check if the default visit_Compare always works ##
	#def visit_Compare(self, node):
	#	raise NotImplementedError( node )


	def visit_AugAssign(self, node):
		self._in_assign_target = True
		target = self.visit( node.target )
		self._in_assign_target = False

		op = '%s=' %self.visit( node.op )

		if op == '//=':
			if isinstance(node.target, ast.Attribute):
				name = self.visit(node.target.value)
				attr = node.target.attr
				target = '%s.%s' %(name, attr)

			if self._with_go:
				a = '%s /= %s' %(target, self.visit(node.value))
			else:
				a = '%s = Math.floor(%s/%s)' %(target, target, self.visit(node.value))
			writer.write(a)


		elif self._with_js:  ## no operator overloading in with-js mode
			a = '%s %s %s' %(target, op, self.visit(node.value))
			writer.write(a)

		elif isinstance(node.target, ast.Attribute):
			name = self.visit(node.target.value)
			attr = node.target.attr
			a = '%s.%s %s %s' %(name, attr, op, self.visit(node.value))
			writer.write(a)

		elif isinstance(node.target, ast.Subscript):
			name = self.visit(node.target.value)
			slice = self.visit(node.target.slice)
			#if self._with_js:
			#	a = '%s[ %s ] %s %s'
			#	writer.write(a %(name, slice, op, self.visit(node.value)))
			#else:
			op = self.visit(node.op)
			value = self.visit(node.value)
			#a = '__get__(%s, "__setitem__")( [%s, __get__(%s, "__getitem__")([%s], {}) %s (%s)], {} )'
			fallback = '__get__(%s, "__setitem__")( [%s, __get__(%s, "__getitem__")([%s], {}) %s (%s)], {} )'%(name, slice, name, slice, op, value)
			if isinstance(node.target.value, ast.Name):
				## TODO also check for arr.remote (RPC) if defined then __setitem__ can not be bypassed

				## the overhead of checking if target is an array,
				## and calling __setitem__ directly bypassing a single __get__,
				## is greather than simply calling the fallback
				#writer.write('if instanceof(%s, Array): %s.__setitem__([%s, %s[%s] %s (%s) ], __NULL_OBJECT__)' %(name, name, slice, name,slice, op, value))

				writer.write('if instanceof(%s, Array): %s[%s] %s= %s' %(name, name,slice, op, value))
				writer.write('else: %s' %fallback)
			else:
				writer.write(fallback)

		else:
			## TODO extra checks to make sure the operator type is valid in this context
			a = '%s %s %s' %(target, op, self.visit(node.value))
			writer.write(a)

	def visit_Yield(self, node):
		return 'yield %s' % self.visit(node.value)

	def _get_js_class_base_init(self, node ):
		for base in node.bases:
			bid = self.visit(base).replace('.','_')
			if bid == 'object':
				continue

			if bid not in self._js_classes:
				print 'WARNING: can not find base class in translation unit <%s>' %bid
				return None

			n = self._js_classes[ bid ]

			if hasattr(n, '_cached_init'):
				return n._cached_init
			else:
				return self._get_js_class_base_init( n )  ## TODO fixme

	def _visit_typed_classdef(self, node): ## this should be called visit_multibackend_classdef
		name = node.name
		node._struct_vars = dict()
		self._js_classes[ name ] = node

		comments = []
		methods  = {}
		method_list = []  ## getter/setters can have the same name
		props = set()     ## type info for the backend and Dart (old)
		struct_types = dict()

		body_macros = []

		for item in node.body:
			if isinstance(item, ast.Expr) and isinstance(item.value, ast.Str):
				comments.append(item.value.s)

			elif isinstance(item, FunctionDef):
				methods[ item.name ] = item
				finfo = inspect_method( item )
				props.update( finfo['properties'] )

				if item.name != '__init__':
					method_list.append( item )

				#if item.name == '__init__': continue
				continue

				item.args.args = item.args.args[1:]  ## remove self
				for n in finfo['name_nodes']:
					if n.id == 'self':
						n.id = 'this'

			elif isinstance(item, ast.Expr) and isinstance(item.value, ast.Dict):
				sdef = []
				for i in range( len(item.value.keys) ):
					k = self.visit( item.value.keys[ i ] )
					v = self.visit( item.value.values[i] )
					sdef.append( '%s=%s'%(k,v) )

				writer.write('@__struct__(%s)' %','.join(sdef))

			elif isinstance(item, ast.Expr) and isinstance(item.value, ast.Call) and isinstance(item.value.func, ast.Name) and item.value.func.id=='macro':
				body_macros.append("macro('%s')" %item.value.args[0].s)


		if comments:
			# Get comment lines.
			comment_lines = comments[0].splitlines()

			# Remove the first and last comment line, if they are empty (could be caused by a multi-line string).
			if len(comment_lines[0].strip()) == 0:
				comment_lines = comment_lines[1:]
			if len(comment_lines) > 1 and len(comment_lines[-1].strip()) == 0:
				comment_lines = comment_lines[:-1]

			# Determine the number of leading whitespaces for the first comment line.
			number_of_leading_whitespaces = len(comment_lines[0]) - len(comment_lines[0].lstrip())

			stripped_comment_lines = []

			# Remove the leading whitespaces from every line (assuming every whitespace starts with the same whitespaces).
			for line in comment_lines:

				# The comment line is too short.
				if len(line) < number_of_leading_whitespaces:
					stripped_comment_lines.append(line.lstrip())
					continue

				# The first part of the comment line does not contain only whitespaces.
				if len(line[:number_of_leading_whitespaces].strip()) > 0:
					stripped_comment_lines.append(line.lstrip())
					continue

				stripped_comment_lines.append(line[number_of_leading_whitespaces:])


			comments = ['\n'.join(stripped_comment_lines)]

		## pass along all class decorators to the backend ##
		for dec in node.decorator_list:
			writer.write('@%s'%self.visit(dec))


		bases = []
		for base in node.bases:
			bases.append( self.visit(base) )
		if bases:
			writer.write('class %s( %s ):'%(node.name, ','.join(bases)))

		else:
			writer.write('class %s:' %node.name)

		init = methods.get( '__init__', None)

		writer.push()

		if comments:
			writer.write("'''%s'''" %comments[0])
		if body_macros:
			for macro in body_macros:
				writer.write(macro)

		## constructor
		if init:
			methods.pop( '__init__' )
			#if self._with_dart:
			#	init.name = node.name

			if not self._with_rust:
				## this is used for which backend? ##
				writer.write('@returns(self)')

			self.visit(init)
			node._struct_vars.update( init._typed_args )

			for item in init.body:
				if isinstance(item, ast.Assign) and isinstance(item.targets[0], ast.Attribute):
					if isinstance(item.targets[0].value, ast.Name) and item.targets[0].value.id=='self':
						attr = item.targets[0].attr
						if attr not in node._struct_vars:
							if self._with_go:
								node._struct_vars[ attr ] = 'interface'
							elif self._with_cpp:
								pass
							else:
								err = [ 
									'error: unknown type for attribute `self.%s`'%attr,
									'init typed args:' + ', '.join(init._typed_args.keys()),
									'struct members :' + ', '.join(node._struct_vars.keys())

								]
								raise SyntaxError( self.format_error('\n'.join(err)) )

				elif isinstance(item, ast.Expr) and isinstance(item.value, ast.Call) and isinstance(item.value.func, ast.Name) and item.value.func.id=='__let__':
					if isinstance(item.value.args[0], ast.Attribute) and item.value.args[0].value.id=='self':
						#node._struct_vars[ item.value.args[0].attr ] = item.value.args[1].s
						node._struct_vars[ item.value.args[0].attr ] = self.visit(item.value.args[1])

		## methods
		for method in method_list:
			self.visit(method)

		for item in node.body:
			if isinstance(item, ast.With):
				s = self.visit(item)
				if s: writer.write( s )


		if not init and not method_list:
			writer.write( 'pass' )

		## this special dict is picked up in the second stage of `pythonjs_to_xxx` to build structs or classes
		if node._struct_vars:
			writer.write('{')
			for k in node._struct_vars:
				v = node._struct_vars[k]
				writer.write('  %s : %s,' %(k,v))
			writer.write('}')

		writer.pull()


	def _visit_js_classdef(self, node):
		name = node.name

		## nested classes 
		if hasattr(node, 'is_nested_class') and node.is_nested_class:
			name = '_'.join( [s.name for s in self._class_stack] )

		self._js_classes[ name ] = node
		self._in_js_class = True
		class_decorators = []

		for decorator in node.decorator_list:  ## class decorators
			class_decorators.append( decorator )

		method_names = []  ## write back in order (required by GLSL)
		methods      = {}  ## same named functions get squashed in here (like getter/setters)
		methods_all  = []  ## all methods of class
		__call__     = None
		class_vars = []
		post_class_write = [
			'%s.prototype.__class__ = %s' %(name, name),
			'%s.__name__ = "%s"' %(name,name),
			'%s.__bases__ = []' %name,
		]
		node._post_class_write = post_class_write
		for item in node.body:
			if isinstance(item, FunctionDef):
				if item.name == '__getattr__':
					raise SyntaxError(self.format_error('__getattr__ is not allowed'))
				## only remove `self` if it is the first argument,
				## python actually allows `self` to be any name (whatever the first argument is named)
				## but that is very bad style, and basically never used.
				## by dropping that bad style we can assume that any method whose first argument is
				## not self is a static method, this way the user can omit using the decorator `@staticmethod`

				item._has_self = False  ## used below to check if it is a staticmethod
				if len(item.args.args):
					item._has_self = self.visit(item.args.args[0]) in ('self', 'this')
				if item._has_self:
					item.args.args = item.args.args[1:]  ## removes self


				finfo = inspect_function( item )

				if item.name == '__call__':
					for n in finfo['name_nodes']:
						if n.id == 'self':
							n.id = '__call__'

					__call__ = item
				else:
					for n in finfo['name_nodes']:
						if n.id == 'self':
							n.id = 'this'

					method_names.append(item.name)
					methods[ item.name ] = item
					methods_all.append( item )

			elif isinstance(item, ast.Expr) and isinstance(item.value, Str):  ## skip doc strings
				pass
			elif isinstance(item, ast.ClassDef):
				## support subclass namespaces ##
				item.is_nested_class = True
				self.visit(item)
				sets_namespace = '.'.join( [s.name for s in self._class_stack+[item]] )
				sub_name = '_'.join( [s.name for s in self._class_stack+[item]] )
				if len(self._class_stack) > 1:
					self._class_stack[0]._post_class_write.insert(0, '%s = %s' %(sets_namespace, sub_name) )
				else:
					post_class_write.insert(0, '%s = %s' %(sets_namespace, sub_name) )

			else:
				class_vars.append( item )


		init = methods.get( '__init__', None)
		if init:
			args = [self.visit(arg) for arg in init.args.args]
			node._cached_init = init
			if init.args.kwarg:
				args.append( init.args.kwarg )

		else:
			args = []
			init = self._get_js_class_base_init( node )
			if init:
				args = [self.visit(arg) for arg in init.args.args]
				node._cached_init = init

		writer.write('def %s(%s):' %(name,','.join(args)))
		writer.push()

		if __call__:
			line = self.visit(__call__)
			if line: writer.write( line )
			writer.write('inline("__call__.__$UID$__ = __$UID$__ ++")')
			#writer.write('__call__.__proto__ = this.__proto__')  ## not valid in all browsers
			## this works in all browsers, and is only slightly slower than using `__proto__`

			for mname in method_names:
				writer.write('__call__.%s = this.%s' %(mname, mname))

			writer.write('__call__.__call__ = __call__')  ## for the rare case, where the user directly call `__call__`
			writer.write('__call__.__class__ = %s' %node.name)  ## so that builtin `isinstance` can still work.

			if init:
				if hasattr(init, '_code'):  ## cached - is this valid here with __call__? ##
					code = init._code
				elif args:
					code = '__call__.__init__(%s)'%(', '.join(args))
					init._code = code
				else:
					code = '__call__.__init__()'
					init._code = code
				writer.write(code)

			writer.write('return __call__')


			if False:
				## this way of implementing a callable functor is 200x slower than above,
				## what is likely killing the JIT here is dynamically binding `__call__` to `this`,
				## looping over the values in `this` and reassigning them to `__callbound__` appears
				## to break V8
				writer.write('var(__callbound__)')
				writer.write('@bind(__callbound__, this)')
				line = self.visit(__call__)
				if line: writer.write( line )
				## note: Object.keys is even slower in this case ##
				#writer.write('inline("for (var _ in Object.keys(this)) {__callbound__[_]=this[_];}")')
				#writer.write('__callbound__.__proto__ = this.__proto__')
				#writer.write('__callbound__.__call__ = __callbound__')
				for mname in method_names:
					writer.write('__callbound__.%s = this.%s.bind(this)' %(mname, mname))
				writer.write('return __callbound__')


		elif init:
			writer.write('inline("this.__$UID$__ = __$UID$__ ++")')

			tail = ''  ## what was tail used for?

			## note: this is just the constructor, the actual __init__
			## body is moved along with all the other methods to functions
			## that bind to CLASSNAME.prototype.METHODNAME
			##for b in init.body:
			##	line = self.visit(b)
			##	if line: writer.write( line )

			if hasattr(init, '_code'):  ## cached ##
				code = init._code
			elif args:
				code = 'this.__init__(%s); %s'%(', '.join(args), tail)
				init._code = code
			else:
				code = 'this.__init__();     %s' % tail
				init._code = code

			writer.write(code)

		else:
			writer.write('inline("this.__$UID$__ = __$UID$__ ++")')

		writer.pull()

		if post_class_write:
			for postline in post_class_write:
				writer.write(postline)


		writer.write('@__prototype__(%s)'%name)
		writer.write('def toString(): return inline("this.__$UID$__")')

		for method in methods_all:
			mname = method.name

			## this hack is required to assign the function to the class prototype `A.prototype.method=function`
			writer.write('@__prototype__(%s)'%name)
			if not method._has_self:
				writer.write('@staticmethod')

			line = self.visit(method)
			if line: writer.write( line )
			#writer.write('%s.prototype.%s = %s'%(name,mname,mname))  ## this also works, but is not as humanreadable

			## allows subclass method to extend the parents method by calling the parent by class name,
			## `MyParentClass.some_method(self)`
			f = 'function () { return %s.prototype.%s.apply(arguments[0], Array.prototype.slice.call(arguments,1)) }' %(name, mname)
			writer.write('%s.%s = inline("%s")'%(name,mname,f))

		for base in node.bases:
			base = self.visit(base)
			if base == 'object': continue
			a = [
				'for (var n in %s.prototype) {'%base,
				'  if (!(n in %s.prototype)) {'%name,
				'    %s.prototype[n] = %s.prototype[n]'%(name,base),
				'  }',
				'}'
			]
			a = ''.join(a)
			writer.write( "inline('%s')" %a )
			writer.write( '%s.__bases__.push(%s)' %(name,base))

		## class attributes
		for item in class_vars:
			if isinstance(item, Assign) and isinstance(item.targets[0], Name):
				item_name = item.targets[0].id
				#item.targets[0].id = '__%s_%s' % (name, item_name)
				#self.visit(item)  # this will output the code for the assign
				#writer.write('%s.prototype.%s = %s' % (name, item_name, item.targets[0].id))
				writer.write('%s.%s = %s' % (name, item_name, self.visit(item.value)))

		self._in_js_class = False

	def visit_ClassDef(self, node):
		self._class_stack.append( node )

		if self._modules:
			writer.write('__new_module__(%s)' %node.name) ## triggers a new file in final stage of translation.

		######## c++ and typed backends ########
		if self._with_go or self._with_rust or self._with_cpp:
			self._visit_typed_classdef(node)
			self._class_stack.pop()
			return

		elif self._with_js:  ######## javascript backend #######
			self._visit_js_classdef(node)
			self._class_stack.pop()
			return


	def visit_And(self, node):
		return ' and '

	def visit_Or(self, node):
		return ' or '

	def visit_BoolOp(self, node):
		op = self.visit(node.op)
		#raise SyntaxError(op)
		return '('+ op.join( [self.visit(v) for v in node.values] ) + ')'

	def visit_If(self, node):
		if writer.is_at_global_level() and (self._with_rust or self._with_rust or self._with_cpp):
			raise SyntaxError( self.format_error('if statements can not be used at module level when transpiling to typed language') )

		elif isinstance(node.test, ast.Dict):
			if self._with_js:
				writer.write('if Object.keys(%s).length:' % self.visit(node.test))
			else:
				writer.write('if %s.keys().length:' % self.visit(node.test))

		elif isinstance(node.test, ast.List):
			writer.write('if %s.length:' % self.visit(node.test))

		elif self._with_ll or self._with_rust or self._with_cpp or self._fast_js:
			writer.write('if %s:' % self.visit(node.test))
		elif isinstance(node.test, ast.Compare):
			writer.write('if %s:' % self.visit(node.test))
		else:
			writer.write('if __test_if_true__(%s):' % self.visit(node.test))

		writer.push()
		map(self.visit, node.body)
		writer.pull()
		if node.orelse:
			writer.write('else:')
			writer.push()
			map(self.visit, node.orelse)
			writer.pull()

	def visit_TryExcept(self, node):
		if len(node.handlers)==0:
			raise SyntaxError(self.format_error('no except handlers'))

		## by default in js-mode some expections will not be raised,
		## this allows those cases to throw proper errors.
		if node.handlers[0].type:
			self._in_catch_exception = self.visit(node.handlers[0].type)
		else:
			self._in_catch_exception = None

		writer.write('try:')
		writer.push()
		map(self.visit, node.body)
		writer.pull()
		map(self.visit, node.handlers)

	def visit_TryFinally(self, node):
		#raise SyntaxError(node.body)
		assert len(node.body)==1
		self.visit_TryExcept(node.body[0])
		writer.write('finally:')
		writer.push()
		for b in node.finalbody:
			a = self.visit(b)
			if a: writer.write(a)
		writer.pull()

	def visit_Raise(self, node):
		if isinstance(node.type, ast.Name):
			writer.write('raise %s' % node.type.id)

		elif isinstance(node.type, ast.Call):
			if len(node.type.args) > 1:
				raise SyntaxError( self.format_error('raise Error(x) can only have a single argument') )
			if node.type.args:
				writer.write( 'raise %s(%s)' %(self.visit(node.type.func), self.visit(node.type.args[0])) )
			else:
				writer.write( 'raise %s()' %self.visit(node.type.func) )

	def visit_ExceptHandler(self, node):
		if node.type and node.name:
			writer.write('except %s, %s:' % (self.visit(node.type), self.visit(node.name)))
		elif node.type and not node.name:
			writer.write('except %s:' % self.visit(node.type))
		else:
			writer.write('except:')
		writer.push()
		map(self.visit, node.body)
		writer.pull()

	def visit_Pass(self, node):
		writer.write('pass')

	def visit_Name(self, node):
		if self._with_js:
			if node.id == 'True':
				return 'true'
			elif node.id == 'False':
				return 'false'
			elif node.id == 'None':
				if self._with_go:
					return 'nil'
				else:
					return 'null'

		return node.id

	def visit_Num(self, node):
		return str(node.n)

	def visit_Return(self, node):
		if node.value:
			if isinstance(node.value, Call) and isinstance(node.value.func, Name) and node.value.func.id in self._classes:
				self._return_type = node.value.func.id
			elif isinstance(node.value, Name) and node.value.id == 'self' and 'self' in self._instances:
				self._return_type = self._instances['self']
			###################

			if isinstance(node.value, ast.Lambda):
				self.visit( node.value )
				writer.write( 'return __lambda__' )

			elif isinstance(node.value, ast.Tuple):
				writer.write( 'return %s;' % ','.join([self.visit(e) for e in node.value.elts]) )

			else:
				writer.write('return %s' % self.visit(node.value))

		else:
			writer.write('return')  ## empty return

	def visit_BinOp(self, node):
		left = self.visit(node.left)
		op = self.visit(node.op)

		is_go_listcomp = False
		if self._with_go:
			if op == '<<':
				if isinstance(node.left, ast.Subscript) and isinstance(node.left.value, ast.Name) and node.left.value.id=='__inline__':
					return 'inline("%s %s")' %(node.left.slice.value.s, self.visit(node.right))

				elif isinstance(node.left, ast.Call) and isinstance(node.left.func, ast.Name):
					if node.left.func.id=='__go__array__' and isinstance(node.right, ast.GeneratorExp):
						is_go_listcomp = True
						node.right.go_listcomp_type = node.left.args[0].id
					elif node.left.func.id=='__go__map__':
						if isinstance(node.left.args[1], ast.Call):  ## map comprehension
							is_go_listcomp = True
							node.right.go_dictcomp_type =  ( node.left.args[0].id, self.visit(node.left.args[1]) )
						else:
							node.right.go_dictcomp_type =  ( node.left.args[0].id, node.left.args[1].id )


		right = self.visit(node.right)

		if self._with_go:
			if op == '//': op = '/'

			if is_go_listcomp:
				return right
			else:
				return '(%s %s %s)' % (left, op, right)

		elif op == '%' and isinstance(node.left, ast.Str) and self._with_js:
			return '__sprintf( %s, %s )' %(left, right)  ## assumes that right is a tuple, or list.

		elif op == '*' and isinstance(node.left, ast.List) and self._with_js:
			if len(node.left.elts) == 1 and isinstance(node.left.elts[0], ast.Name) and node.left.elts[0].id == 'None':
				return 'inline("new Array(%s)")' %self.visit(node.right)
			else:
				return '%s.__mul__(%s)' %(left, right)

		elif op == '//' and self._with_js:
			return 'Math.floor(%s/%s)' %(left, right)

		elif op == '**' and self._with_js:
			return 'Math.pow(%s,%s)' %(left, right)


		return '(%s %s %s)' % (left, op, right)

	def visit_Eq(self, node):
		return '=='

	def visit_NotEq(self, node):
		return '!='

	def visit_Is(self, node):
		return 'is'

	def visit_Pow(self, node):
		return '**'

	def visit_Mult(self, node):
		return '*'

	def visit_Add(self, node):
		return '+'

	def visit_Sub(self, node):
		return '-'

	def visit_FloorDiv(self, node):
		return '//'
	def visit_Div(self, node):
		return '/'
	def visit_Mod(self, node):
		return '%'
	def visit_LShift(self, node):
		return '<<'
	def visit_RShift(self, node):
		return '>>'
	def visit_BitXor(self, node):
		return '^'
	def visit_BitOr(self, node):
		return '|'
	def visit_BitAnd(self, node):
		return '&'

	def visit_Lt(self, node):
		return '<'

	def visit_Gt(self, node):
		return '>'

	def visit_GtE(self, node):
		return '>='

	def visit_LtE(self, node):
		return '<='

	def visit_Compare(self, node):
		left = self.visit(node.left)
		comp = [ left ]
		for i in range( len(node.ops) ):
			if i==0 and isinstance(node.left, ast.Name) and node.left.id in self._typedef_vars and self._typedef_vars[node.left.id] == 'long':
				if isinstance(node.ops[i], ast.Eq):
					comp = ['%s.equals(%s)' %(left, self.visit(node.comparators[i]))]
				elif isinstance(node.ops[i], ast.Lt):
					comp = ['%s.lessThan(%s)' %(left, self.visit(node.comparators[i]))]
				elif isinstance(node.ops[i], ast.Gt):
					comp = ['%s.greaterThan(%s)' %(left, self.visit(node.comparators[i]))]

				elif isinstance(node.ops[i], ast.LtE):
					comp = ['%s.lessThanOrEqual(%s)' %(left, self.visit(node.comparators[i]))]
				elif isinstance(node.ops[i], ast.GtE):
					comp = ['%s.greaterThanOrEqual(%s)' %(left, self.visit(node.comparators[i]))]

				else:
					raise NotImplementedError( node.ops[i] )

			elif isinstance(node.ops[i], ast.In) or isinstance(node.ops[i], ast.NotIn):
				if comp[-1] == left:
					comp.pop()
				else:
					comp.append( ' and ' )

				if isinstance(node.ops[i], ast.NotIn):
					comp.append( ' not (')

				a = ( self.visit(node.comparators[i]), left )

				if self._with_cpp or self._with_rust or self._with_go:
					comp.append('%s in %s' %(a[1], a[0]))

				elif self._with_js:
					## this makes "if 'x' in Array" work like Python: "if 'x' in list" - TODO fix this for js-objects
					## note javascript rules are confusing: "1 in [1,2]" is true, this is because a "in test" in javascript tests for an index
					comp.append( '__contains__(%s, %s)' %(a[0],a[1]))
				else:
					raise RuntimeError( self.format_error('invalid backend') )

				if isinstance(node.ops[i], ast.NotIn):
					comp.append( ' )')  ## it is not required to enclose NotIn

			else:
				comp.append( self.visit(node.ops[i]) )
				comp.append( self.visit(node.comparators[i]) )

		try:
			out = ' '.join(comp)
		except UnicodeDecodeError as err:
			print comp
			for c in comp:
				print c
			raise err
		return ' '.join( comp )

	def visit_Not(self, node):
		return ' not '

	def visit_IsNot(self, node):
		return ' is not '

	def visit_UnaryOp(self, node):
		op = self.visit(node.op)
		if op is None: raise RuntimeError( node.op )
		operand = self.visit(node.operand)
		if operand is None: raise RuntimeError( node.operand )
		return op + operand

	def visit_USub(self, node):
		return '-'
	def visit_UAdd(self, node):
		return '+'


	def visit_Attribute(self, node):
		node_value = self.visit(node.value)

		if self._with_ll or self._with_go:
			return '%s.%s' %(node_value, node.attr)

		elif self._with_js:
			## TODO enable get attribute - move to js backend ##
			#if self._in_catch_exception == 'AttributeError':
			#	return '__getfast__(%s, "%s")' % (node_value, node.attr)
			#else:
			return '%s.%s' %(node_value, node.attr)

		elif hasattr(node, 'lineno'):
			src = self._source[ node.lineno-1 ]
			src = src.replace('"', '\\"')
			err = 'missing attribute `%s` - line %s: %s'	%(node.attr, node.lineno, src.strip())
			return '__get__(%s, "%s", "%s")' % (node_value, node.attr, err)
		else:
			return '__get__(%s, "%s")' % (node_value, node.attr)


	def visit_Index(self, node):
		return self.visit(node.value)

	def visit_Subscript(self, node):
		name = self.visit(node.value)

		if isinstance(node.slice, ast.Ellipsis):
			return '%s[...]' %name

		elif self._with_ll or self._with_rust or self._with_go or self._with_cpp:
			return '%s[%s]' %(name, self.visit(node.slice))

		elif self._with_js:
			if isinstance(node.slice, ast.Slice):  ## allow slice on Array
				if not node.slice.lower and not node.slice.upper and not node.slice.step:
					return '%s.copy()' %name
				elif not node.slice.upper and node.slice.step:
					slice = self.visit(node.slice).split(',')
					slice = '%s,%s' %(slice[0], slice[2])
					return '%s.__getslice_lowerstep__(%s)'%(name, slice)
				else:
					return '%s.__getslice__(%s)'%(name, self.visit(node.slice))


			elif isinstance(node.slice, ast.Index) and isinstance(node.slice.value, ast.Num):
				if node.slice.value.n < 0:
					## the problem with this is it could be a dict with negative numbered keys
					return '%s[ %s.length+%s ]' %(name, name, self.visit(node.slice))
				else:
					return '%s[ %s ]' %(name, self.visit(node.slice))


			else:  ## ------------------ old javascript mode ------------------------
				## TODO clean this up ##

				if self._in_catch_exception == 'KeyError':
					value = self.visit(node.value)
					slice = self.visit(node.slice)
					return '__get__(%s, "__getitem__")([%s], __NULL_OBJECT__)' % (value, slice)

				elif isinstance(node.slice, ast.Index) and isinstance(node.slice.value, ast.BinOp):
					## TODO keep this optimization? in js mode `a[x+y]` is assumed to a direct key,
					## it would be safer to check if one of the operands is a number literal,
					## in that case it is safe to assume that this is a direct key.
					return '%s[ %s ]' %(name, self.visit(node.slice))

				elif self._with_direct_keys:
					return '%s[ %s ]' %(name, self.visit(node.slice))

				else:
					s = self.visit(node.slice)
					## this is bad for chromes jit because it trys to find `__uid__`
					return '%s[ __ternary_operator__(%s.__uid__, %s) ]' %(name, s, s)

					## TODO check why the JSON.stringify hack fails with arrays (fake tuples)
					#check_array = '__ternary_operator__( instanceof(%s,Array), JSON.stringify(%s), %s )' %(s, s, s)
					#return '%s[ __ternary_operator__(%s.__uid__, %s) ]' %(name, s, check_array)

		else:
			raise RuntimeError( self.format_error('unknown backend') )

	def visit_Slice(self, node):
		if self._with_go or self._with_rust or self._with_cpp:
			lower = upper = step = None
		elif self._with_js:
			lower = upper = step = 'undefined'
		else:
			lower = upper = step = 'undefined'
		if node.lower:
			lower = self.visit(node.lower)
		if node.upper:
			upper = self.visit(node.upper)
		if node.step:
			step = self.visit(node.step)

		if self._with_go or self._with_rust or self._with_cpp:
			if lower and upper and step:
				return '%s:%s:%s' %(lower,upper,step)
			elif lower and step:
				return '%s::%s' %(lower,step)
			elif upper and step:
				return ':%s:%s' %(upper,step)
			elif step:
				return '::%s'%step
			elif lower and upper:
				return '%s:%s' %(lower,upper)
			elif upper:
				return ':%s' %upper
			elif lower:
				return '%s:'%lower
			else:
				return ':'
		else:
			return "%s, %s, %s" % (lower, upper, step)

	def visit_Assign(self, node):
		use_runtime_errors = not (self._with_js or self._with_ll or self._with_go)
		use_runtime_errors = use_runtime_errors and self._with_runtime_exceptions

		lineno = node.lineno
		if node.lineno < len(self._source):
			src = self._source[ node.lineno ]
			self._line_number = node.lineno
			self._line = src


		if use_runtime_errors:
			writer.write('try:')
			writer.push()

		targets = list( node.targets )
		target = targets[0]

		## should be ok most of the time to assign to a low level type, TODO deprecate this when `auto dict = x` is fixed c++ backend.
		if isinstance(target, ast.Name) and target.id in typedpython.types:
			raise SyntaxError( self.format_error('ERROR: can not assign to builtin lowlevel type: '+target.id) )

		elif self._with_go and isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name) and target.value.id in ('__go__array__', '__go__class__', '__go__pointer__', '__go__func__'):
			if len(targets)==2 and isinstance(targets[1], ast.Attribute) and isinstance(targets[1].value, ast.Name) and targets[1].value.id == 'self' and len(self._class_stack):
				if target.value.id == '__go__array__':
					self._class_stack[-1]._struct_vars[ targets[1].attr ] = '__go__array__(%s<<typedef)' %self.visit(target.slice)
				elif target.value.id == '__go__class__':
					self._class_stack[-1]._struct_vars[ targets[1].attr ] = self.visit(target.slice)
				elif target.value.id == '__go__pointer__':
					self._class_stack[-1]._struct_vars[ targets[1].attr ] = '"*%s"' %self.visit(target.slice)
				elif target.value.id == '__go__func__':
					self._class_stack[-1]._struct_vars[ targets[1].attr ] = self.visit(target.slice)


			elif target.value.id == '__go__class__':
				#self._class_stack[-1]._struct_vars[ targets[1].attr ] = self.visit(target.slice)
				raise SyntaxError(self.visit(target))
			elif target.value.id == '__go__pointer__':
				if len(targets)==2:
					writer.write(
						'inline("var %s *%s;")' %(self.visit(targets[1]), self.visit(target.slice))
					)
				else:
					writer.write(
						'inline("var %s *%s;")' %(self.visit(node.value), self.visit(target.slice))
					)

			elif target.value.id == '__go__array__':
				if isinstance(node.value, ast.Call) and len(node.value.args) and isinstance(node.value.args[0], ast.GeneratorExp ):
					node.value.args[0].go_listcomp_type = self.visit(target.slice)
				else:
					raise SyntaxError( 'only a variable created by a generator expressions needs an array typedef')
			else:
				raise SyntaxError(self.visit(target))

			targets = targets[1:]


		elif self._with_rpc_name and isinstance(target, Attribute) and isinstance(target.value, Name) and target.value.id == self._with_rpc_name:
			writer.write('__rpc_set__(%s, "%s", %s)' %(self._with_rpc, target.attr, self.visit(node.value)))
			return None
		elif self._with_rpc_name and isinstance(node.value, Attribute) and isinstance(node.value.value, Name) and node.value.value.id == self._with_rpc_name:
			writer.write('%s = __rpc_get__(%s, "%s")' %(self.visit(target), self._with_rpc, node.value.attr))
			return None

		#############################################
		for target in targets:
			self._visit_assign_helper( node, target )
			node = ast.Expr( value=target )

		if use_runtime_errors:
			writer.pull()
			writer.write('except:')
			writer.push()
			if lineno-1 < len(self._source):
				src = self._source[ lineno-1 ]
				src = src.replace('"', '\\"')
				src = 'line %s: %s'	%(lineno, src.strip())
				writer.write('console.trace()')
				writer.write('console.error(__exception__, __exception__.message)')
				writer.write('console.error("""%s""")' %src)
				writer.write('raise RuntimeError("""%s""")' %src)
			else:
				writer.write('raise RuntimeError("no source code")')

			writer.pull()



	def _visit_assign_helper(self, node, target):
		if isinstance(node.value, ast.Lambda):
			self.visit(node.value)  ## writes function def
			writer.write('%s = __lambda__' %self.visit(target))

		elif isinstance(node.value, ast.Dict) and (self._with_go or self._with_rust or self._with_cpp):
			key_type = None
			val_type = None

			for i in range( len(node.value.keys) ):
				k = node.value.keys[ i ]
				v = node.value.values[i]
				if isinstance(k, ast.Str):
					key_type = 'string'
				elif isinstance(k, ast.Num):
					key_type = 'int'

				if isinstance(v, ast.Str):
					val_type = 'string'
				elif isinstance(v, ast.Num):
					if isinstance(v.n, int):
						val_type = 'int'
					else:
						val_type = 'float64'

			if not key_type:
				raise SyntaxError(  self.format_error('can not determine dict key type')  )
			if not val_type:
				raise SyntaxError(  self.format_error('can not determine dict value type')  )

			t = self.visit(target)
			v = self.visit(node.value)
			writer.write('%s = __go__map__(%s, %s) << %s' %(t, key_type, val_type, v))
			self._autotyped_dicts[t] = v


		elif isinstance(node.value, ast.List) and (self._with_go or self._with_rust or self._with_cpp):
			guess_type = None
			for elt in node.value.elts:
				if isinstance(elt, ast.Num):
					if isinstance(elt.n, int):
						guess_type = 'int'
					else:
						guess_type = 'float64'
				elif isinstance(elt, ast.Str):
					guess_type = 'string'

			if guess_type:
				t = self.visit(target)
				v = self.visit(node.value)
				writer.write('%s = __go__array__(%s) << %s' %(t, guess_type, v))
			else:
				raise SyntaxError(self.format_error('can not determine type of array'))

		elif isinstance(target, Subscript):
			name = self.visit(target.value)  ## target.value may have "returns_type" after being visited

			if isinstance(target.slice, ast.Ellipsis):
				#code = '%s["$wrapped"] = %s' %(self.visit(target.value), self.visit(node.value))
				code = '%s[...] = %s' %(self.visit(target.value), self.visit(node.value))

			elif isinstance(target.slice, ast.Slice):
				if isinstance(target.value, ast.Name) and target.value.id == '__let__':
					## pass along special __let__ to the backend pass
					code = '__let__[%s : %s]' %(self.visit(target.slice.upper), self.visit(target.slice.lower))
				elif self._with_cpp or self._with_rust or self._with_go:
					code = '%s[%s]=%s' %(self.visit(target.value), self.visit(target.slice), self.visit(node.value))
				else:
					code = '%s.__setslice__(%s, %s)' %(self.visit(target.value), self.visit(target.slice), self.visit(node.value))

			elif self._with_ll or self._with_cpp or self._with_go or self._with_rust:
				code = '%s[ %s ] = %s'
				code = code % (self.visit(target.value), self.visit(target.slice.value), self.visit(node.value))

			elif self._with_js:
				s = self.visit(target.slice.value)
				if isinstance(target.slice.value, ast.Num) or isinstance(target.slice.value, ast.BinOp):
					code = '%s[ %s ] = %s' % (self.visit(target.value), s, self.visit(node.value))
				elif self._with_direct_keys:
					code = '%s[ %s ] = %s' % (self.visit(target.value), s, self.visit(node.value))
				else:
					## check_array is broken? TODO deprecate or fix this
					#check_array = '__ternary_operator__( instanceof(%s,Array), JSON.stringify(%s), %s )' %(s, s, s)
					#code = '%s[ __ternary_operator__(%s.__uid__, %s) ] = %s' %(self.visit(target.value), s, check_array, self.visit(node.value))
					## this is safer
					code = '%s[ __ternary_operator__(%s.__uid__, %s) ] = %s' %(self.visit(target.value), s, s, self.visit(node.value))

			elif name in self._func_typedefs and self._func_typedefs[name] == 'list':
				code = '%s[%s] = %s'%(name, self.visit(target.slice.value), self.visit(node.value))

			else:
				code = "__get__(__get__(%s, '__setitem__'), '__call__')([%s, %s], JSObject())"
				code = code % (self.visit(target.value), self.visit(target.slice.value), self.visit(node.value))

			writer.write(code)

		elif isinstance(target, Attribute):
			self._in_assign_target = True
			target_value = self.visit(target.value)  ## target.value may have "returns_type" after being visited
			self._in_assign_target = False

			if self._with_js or self._with_go:
				writer.write( '%s.%s=%s' %(target_value, target.attr, self.visit(node.value)) )

		elif isinstance(target, Name):  ## assignment to variable
			node_value = self.visit( node.value )  ## node.value may have extra attributes after being visited

			## note: self._globals and self._instances is DEPRECATED
			## tracking of variable types has been moved to the next stage of translation,
			## where each backend may have different requirements.

			writer.write('%s = %s' % (self.visit(target), node_value))

		elif isinstance(target, ast.Tuple):
			if self._use_destructured_assignment:  ## Rust, Go, Dart
				elts = [self.visit(e) for e in target.elts]
				writer.write('(%s) = %s' % (','.join(elts), self.visit(node.value)))

			elif self._with_cpp and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name) and node.value.func.id=='channel':
				## special case for rust style channels
				sender = self.visit( target.elts[0] )
				recver = self.visit( target.elts[1] )
				writer.write('%s = %s' % (sender, self.visit(node.value)))
				writer.write('%s = %s' % (recver, sender))

			else:
				if isinstance(node.value, ast.Name):
					r = node.value.id
				else:
					id = self.identifier
					self.identifier += 1
					r = '__r_%s' % id
					writer.write('var(%s)' % r)
					writer.write('%s = %s' % (r, self.visit(node.value)))

				for i, target in enumerate(target.elts):
					if isinstance(target, Attribute):
						code = '__set__(%s, "%s", %s[%s])' % (
							self.visit(target.value),
							target.attr,
							r,
							i
						)
						writer.write(code)
					elif self._with_js:
						writer.write("%s = %s[%s]" % (self.visit(target), r, i))
					else:
						raise RuntimeError( self.format_error('unknown backend'))

		else:
			raise SyntaxError( self.format_error(target) )


	def visit_Print(self, node):
		writer.write('print(%s)' % ', '.join(map(self.visit, node.values)))

	def visit_Str(self, node):
		s = node.s.replace('\\','\\\\').replace('\n', '\\n').replace('\r', '\\r').replace('\0', '\\0')
		s = s.replace('\"', '\\"')
		s = s.replace('.__right_arrow__.', '->').replace('= __go__send__<<', '<-')
		s = s.replace('__DOLLAR__', '$')
		s = s.replace('__new__>>', 'new ')
		s = s.replace('.__doublecolon__.', '::')


		if self._with_js:
			return '"%s"' %s           #.encode('utf-8')
		else:
			if len(s) == 0:
				return '""'
			elif s.startswith('"') or s.endswith('"'):
				return "'''%s'''" %s   #.encode('utf-8')
			else:
				return '"""%s"""' %s   #.encode('utf-8')

	def visit_IfExp(self, node):
		test    = self.visit(node.test)
		iftrue  = self.visit(node.body)
		iffalse = self.visit(node.orelse)
		return '(%s if %s else %s)' %(iftrue, test, iffalse)


	def visit_Expr(self, node):
		if node.lineno < len(self._source):
			src = self._source[ node.lineno ]
			## TODO raise SyntaxErrors with the line number and line source
			self._line_number = node.lineno
			self._line = src

		## note: runtime errors and checking generator has moved to `jstranslator.md`
		## TODO clean this up
		#use_runtime_errors = not (self._with_js or self._with_ll or self._with_dart or self._with_coffee or self._with_go)
		#use_runtime_errors = use_runtime_errors and self._with_runtime_exceptions

		line = self.visit(node.value)
		if line:
			#writer.write('('+line+')')
			writer.write( line )


	def visit_Call(self, node):
		if isinstance(node.func, ast.Lambda):  ## inlined and called lambda "(lambda x: x)(y)"
			node.func.keep_as_lambda = True

		for a in node.args:
			if isinstance(a, ast.Lambda):
				a.keep_as_lambda = True

		for kw in node.keywords:
			if isinstance(kw.value, ast.Lambda):
				kw.value.keep_as_lambda = True


		name = self.visit(node.func)
		if name in typedpython.GO_SPECIAL_CALLS:
			name = typedpython.GO_SPECIAL_CALLS[ name ]
			args = [self.visit(e) for e in node.args ]
			args += ['%s=%s' %(k.arg, self.visit(k.value)) for k in node.keywords ]
			return '%s( %s )' %(name, ','.join(args))

		if self._with_rpc:
			if not self._with_rpc_name:
				return '__rpc__( %s, "%s", [%s] )' %(self._with_rpc, name, ','.join([self.visit(a) for a in node.args]))
			elif self._with_rpc_name:
				if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, Name) and node.func.value.id == self._with_rpc_name:
					name = name[ len(self._with_rpc_name)+1 : ]
					return '__rpc__( %s, "%s", [%s] )' %(self._with_rpc, name, ','.join([self.visit(a) for a in node.args]))

		###############################################

		if name == 'open':  ## do not overwrite window.open ##
			name = '__open__'
			node.func.id = '__open__'

		###############################################

		if self._with_webworker and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, Name) and node.func.value.id == 'self' and node.func.attr == 'terminate':
			return 'self.postMessage({"type":"terminate"})'

		elif self._use_threading and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, Name) and node.func.value.id == 'threading':
			if node.func.attr == 'start_new_thread' or node.func.attr == '_start_new_thread':
				return '__start_new_thread( %s, %s )' %(self.visit(node.args[0]), self.visit(node.args[1]))
			elif node.func.attr == 'start_webworker':
				return '__start_new_thread( %s, %s )' %(self.visit(node.args[0]), self.visit(node.args[1]))
			else:
				raise SyntaxError( self.format_error(node.func.attr) )

		elif self._with_webworker and name in self._global_functions:
			node.calling_from_worker = True
			args = [self.visit(arg) for arg in node.args]
			return 'self.postMessage({"type":"call", "function":"%s", "args":[%s]})' %(name, ','.join(args))

		elif self._with_js and self._use_array and name == 'array':
			args = [self.visit(arg) for arg in node.args]
			return '__js_typed_array(%s)' %','.join(args)

		#########################################
		if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, Name) and node.func.value.id == 'numpy' and node.func.attr == 'array':
			args = [self.visit(arg) for arg in node.args]
			if node.keywords:
				kwargs = [ '%s=%s' %(x.arg, self.visit(x.value)) for x in node.keywords]
				return 'numpy.array(%s, %s)' %( ','.join(args), ','.join(kwargs) )
			else:
				return 'numpy.array(%s)' %','.join(args)

		elif isinstance(node.func, ast.Attribute) and isinstance(node.func.value, Name) and node.func.value.id == 'pythonjs' and node.func.attr == 'configure':
			raise RuntimeError( self.format_error('pythonjs.configure is deprecated'))

		elif name == 'inline':
			return 'inline(%s)' %self.visit(node.args[0])

		elif self._with_ll:
			F = self.visit(node.func)
			args = [self.visit(arg) for arg in node.args]
			if node.keywords:
				args.extend( [self.visit(x.value) for x in node.keywords] )
				return '%s(%s)' %( F, ','.join(args) )
			else:
				return '%s(%s)' %( F, ','.join(args) )

		elif self._with_go or self._with_rust or self._with_cpp:  ## pass-thru unchanged to next stage for Go, Rust and C++
			args = list( map(self.visit, node.args) )
			if None in args:
				raise RuntimeError( self.format_error('invalid argument: %s' %node.args))
			if node.keywords:
				args.extend( ['%s=%s'%(x.arg,self.visit(x.value)) for x in node.keywords] )
			if node.starargs:
				args.append('*%s' %self.visit(node.starargs))

			return '%s(%s)' %( self.visit(node.func), ','.join(args) )

		elif self._with_js:
			args = list( map(self.visit, node.args) )

			if name in self._generator_functions:
				return ' new(%s(%s))' %(name, ','.join(args))

			elif name in self._builtin_functions and self._builtin_functions[name]:  ## inlined js
				if args:
					return self._builtin_functions[name] % ','.join(args)
				else:
					return self._builtin_functions[name]

			elif name == 'new':
				assert len(args) == 1
				return 'new(%s)' %args[0]

			elif name == 'isinstance':
				assert len(args) == 2
				#if args[1] == 'dict':   ## TODO find better solution for dict test
				#	args[1] = 'Object'  ## this fails when testing "isinstance(a, dict)==False" when a is an instance of some class.
				#elif args[1] == 'list':
				#	args[1] = 'Array'
				return 'isinstance(%s, %s)' %(args[0], args[1])

			elif isinstance(node.func, ast.Attribute):
				## special method calls that collide with javascript internal methods on native types ##
				anode = node.func
				self._in_assign_target = True
				method = self.visit( node.func )
				self._in_assign_target = False

				if anode.attr == 'update' and len(args) == 1:
					return '__jsdict_update(%s, %s)' %(self.visit(anode.value), ','.join(args) )

				elif anode.attr == 'get' and len(args) > 0 and len(args) <= 2 and not node.keywords:
					return '__jsdict_get(%s, %s)' %(self.visit(anode.value), ','.join(args) )

				elif anode.attr == 'set' and len(args)==2:
					return '__jsdict_set(%s, %s)' %(self.visit(anode.value), ','.join(args))

				elif anode.attr == 'keys' and not args:
					#if self._strict_mode:
					#	raise SyntaxError( self.format_error('method `keys` is not allowed without arguments') )

					return '__jsdict_keys(%s)' %self.visit(anode.value)

				elif anode.attr == 'values' and not args:
					#if self._strict_mode:
					#	raise SyntaxError( self.format_error('method `values` is not allowed without arguments') )
					return '__jsdict_values(%s)' %self.visit(anode.value)

				elif anode.attr == 'items' and not args and not node.keywords:
					#if self._strict_mode:
					#	raise SyntaxError( self.format_error('method `items` is not allowed without arguments') )

					return '__jsdict_items(%s)' %self.visit(anode.value)

				elif anode.attr == 'pop' and len(args) in (1,2):
					pval  = self.visit(anode.value)
					pargs = ','.join(args)
					## special case for `myarray.pop(0)`, all cases of `myarr.pop(n)` see `__jsdict_pop`
					if len(args)==1 and isinstance(anode.value, ast.Name) and args[0]=='0':  ## V8 can JIT this
						return '(%s.shift() if instanceof(%s,Array) else __jsdict_pop(%s, %s))' %(pval, pval, pval,pargs)
					else:
						return '__jsdict_pop(%s, %s)' %(pval, ','.join(args) )

				elif anode.attr == 'split' and not args:
					if self._strict_mode:
						raise SyntaxError( self.format_error('method `split` is not allowed without arguments') )

					return '__split_method(%s)' %self.visit(anode.value)

				elif anode.attr == 'sort' and not args:
					if self._strict_mode:
						raise SyntaxError( self.format_error('method `sort` is not allowed without arguments') )

					return '__sort_method(%s)' %self.visit(anode.value)

				elif anode.attr == 'replace' and len(node.args)==2:
					if self._strict_mode:
						raise SyntaxError( self.format_error('method `replace` is not allowed...') )

					return '__replace_method(%s, %s)' %(self.visit(anode.value), ','.join(args) )

				else:
					ctx = '.'.join( self.visit(node.func).split('.')[:-1] )
					if node.keywords:
						kwargs = [ '%s:%s'%(x.arg, self.visit(x.value)) for x in node.keywords ]

						if args:
							if node.starargs:
								a = ( method, ctx, ','.join(args), self.visit(node.starargs), ','.join(kwargs) )
								## note: this depends on the fact that [].extend in PythonJS returns self (this),
								## which is different from regular python where list.extend returns None
								return '%s.apply( %s, [].extend([%s]).extend(%s).append({%s}) )' %a
							else:
								return '%s(%s, {%s})' %( method, ','.join(args), ','.join(kwargs) )

						else:
							if node.starargs:
								a = ( self.visit(node.func),ctx, self.visit(node.starargs), ','.join(kwargs) )
								return '%s.apply(%s, [].extend(%s).append({%s}) )' %a

							else:
								return '%s({%s})' %( method, ','.join(kwargs) )

					else:
						if node.starargs:
							a = ( self.visit(node.func), ctx, ','.join(args), self.visit(node.starargs) )
							return '%s.apply(%s, [].extend([%s]).extend(%s))' %a

						else:
							return '%s(%s)' %( method, ','.join(args) )


			elif isinstance(node.func, Name) and node.func.id in self._js_classes:
				if node.keywords:
					kwargs = [ '%s:%s'%(x.arg, self.visit(x.value)) for x in node.keywords ]
					if args:
						a = ','.join(args)
						return 'new( %s(%s, {%s}) )' %( self.visit(node.func), a, ','.join(kwargs) )
					else:
						return 'new( %s({%s}) )' %( self.visit(node.func), ','.join(kwargs) )
				else:
					if node.kwargs:
						args.append( self.visit(node.kwargs) )

					a = ','.join(args)
					return 'new( %s(%s) )' %( self.visit(node.func), a )

			else:  ## ----------------------------- javascript mode ------------------------
				if node.keywords:
					kwargs = [ '%s:%s'%(x.arg, self.visit(x.value)) for x in node.keywords ]
					if args:
						if node.starargs:
							a = ( self.visit(node.func), self.visit(node.func), ','.join(args), self.visit(node.starargs), ','.join(kwargs) )
							return '%s.apply( %s, [].extend([%s]).extend(%s).append({%s}) )' %a
						else:
							return '%s(%s, {%s})' %( self.visit(node.func), ','.join(args), ','.join(kwargs) )
					else:
						if node.starargs:
							a = ( self.visit(node.func),self.visit(node.func), self.visit(node.starargs), ','.join(kwargs) )
							return '%s.apply(%s, [].extend(%s).append({%s}) )' %a
						else:
							func_name = self.visit(node.func)
							if func_name == 'dict':
								return '{%s}' %','.join(kwargs)
							else:
								return '%s({%s})' %( func_name, ','.join(kwargs) )

				else:
					if node.starargs:
						a = ( self.visit(node.func), self.visit(node.func), ','.join(args), self.visit(node.starargs) )
						return '%s.apply(%s, [].extend([%s]).extend(%s))' %a
					else:
						return '%s(%s)' %( self.visit(node.func), ','.join(args) )


		elif isinstance(node.func, Name) and node.func.id in self._generator_functions:
			args = list( map(self.visit, node.args) )
			if name in self._generator_functions:
				return 'JS("new %s(%s)")' %(name, ','.join(args))

		elif name == 'new':
			args = list( map(self.visit, node.args) )
			assert len(args) == 1
			return 'new(%s)' %args[0]

		elif isinstance(node.func, Name) and node.func.id in ('JS', 'toString', 'JSObject', 'JSArray', 'var', 'instanceof', 'typeof'):
			args = list( map(self.visit, node.args) ) ## map in py3 returns an iterator not a list
			if node.func.id == 'var':
				for k in node.keywords:
					self._instances[ k.arg ] = k.value.id
					args.append( k.arg )
			else:
				kwargs = map(lambda x: '%s=%s' % (x.arg, self.visit(x.value)), node.keywords)
				args.extend(kwargs)
			args = ', '.join(args)
			return '%s(%s)' % (node.func.id, args)

		else:
			## TODO deprecate below ##

			## check if pushing to a global typed list ##
			if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, Name) and node.func.value.id in self._global_typed_lists and node.func.attr == 'append':
				gtype = self._globals[ node.func.value.id ]
				if gtype == 'list' and node.func.attr == 'append':
					if isinstance(node.args[0], Name):
						if node.args[0].id in self._instances:
							gset = self._global_typed_lists[ node.func.value.id ]
							gset.add( self._instances[node.args[0].id])
							if len(gset) != 1:
								raise SyntaxError('global lists can only contain one type: instance "%s" is different' %node.args[0].id)
						else:
							raise SyntaxError('global lists can only contain one type: instance "%s" is unknown' %node.args[0].id)

			call_has_args_only = len(node.args) and not (len(node.keywords) or node.starargs or node.kwargs)
			call_has_args_kwargs_only = len(node.args) and len(node.keywords) and not (node.starargs or node.kwargs)
			call_has_args = len(node.args) or len(node.keywords) or node.starargs or node.kwargs
			name = self.visit(node.func)
			args = None
			kwargs = None

			if call_has_args_only:  ## lambda only supports simple args for now.
				args = ', '.join(map(self.visit, node.args))

			elif call_has_args_kwargs_only:
				args = ', '.join(map(self.visit, node.args))
				kwargs = ', '.join(map(lambda x: '%s:%s' % (x.arg, self.visit(x.value)), node.keywords))

			elif call_has_args:
				args = ', '.join(map(self.visit, node.args))
				kwargs = ', '.join(map(lambda x: '%s=%s' % (x.arg, self.visit(x.value)), node.keywords))
				args_name = '__args_%s' % self.identifier
				kwargs_name = '__kwargs_%s' % self.identifier

				writer.append('var(%s, %s)' % (args_name, kwargs_name))
				self.identifier += 1

				writer.append('%s = [%s]' % (args_name, args))

				if node.starargs:
					writer.append('%s.push.apply(%s, %s)' % (args_name, args_name, self.visit(node.starargs)))

				writer.append('%s = JSObject(%s)' % (kwargs_name, kwargs))

				if node.kwargs:
					kwargs = self.visit(node.kwargs)
					writer.write('var(__kwargs_temp)')
					writer.write('__kwargs_temp = %s[...]' %kwargs)
					#code = "JS('for (var name in %s) { %s[name] = %s[...][name]; }')" % (kwargs, kwargs_name, kwargs)
					#code = "for __name in %s: %s[__name] = %s[__name]" % (kwargs, kwargs_name, kwargs)
					code = "JS('for (var name in __kwargs_temp) { %s[name] = __kwargs_temp[name]; }')" %kwargs_name
					writer.append(code)

			#######################################

			## special method calls ##
			if isinstance(node.func, ast.Attribute) and node.func.attr in ('get', 'keys', 'values', 'pop', 'items', 'split', 'replace', 'sort'):
				anode = node.func
				if anode.attr == 'get' and len(node.args) > 0 and len(node.args) <= 2:
					return '__jsdict_get(%s, %s)' %(self.visit(anode.value), args )

				elif anode.attr == 'keys' and not args:
					return '__jsdict_keys(%s)' %self.visit(anode.value)

				elif anode.attr == 'values' and not args:
					return '__jsdict_values(%s)' %self.visit(anode.value)

				elif anode.attr == 'items' and not args:
					return '__jsdict_items(%s)' %self.visit(anode.value)

				elif anode.attr == 'pop':
					if args:
						return '__jsdict_pop(%s, %s)' %(self.visit(anode.value), args )
					else:
						return '__jsdict_pop(%s)' %self.visit(anode.value)

				elif anode.attr == 'sort' and not args:
					return '__sort_method(%s)' %self.visit(anode.value)

				elif anode.attr == 'split' and len(node.args) <= 1:
					if not args:
						return '__split_method(%s)' %self.visit(anode.value)
					else:
						return '__split_method(%s, %s)' %(self.visit(anode.value), args)

				elif anode.attr == 'replace' and len(node.args)==2:
					return '__replace_method(%s, %s)' %(self.visit(anode.value), args )

				else:
					return '%s(%s)' %( self.visit(node.func), args )


	def visit_Lambda(self, node):
		args = []
		for i,a in  enumerate(node.args.args):  ## typed args lambda hack
			s = self.visit(a)
			if len(node.args.defaults):
				assert len(node.args.args)==len(node.args.defaults)
				s += '="%s"' %self.visit(node.args.defaults[i])
			args.append( s )


		##'__INLINE_FUNCTION__' from typedpython.py
		if hasattr(node, 'keep_as_lambda') or (args and args[0]=='__INLINE_FUNCTION__'):
			## TODO lambda keyword args
			self._in_lambda = True
			a = '(lambda %s: %s)' %(','.join(args), self.visit(node.body))
			self._in_lambda = False
			return a
		else:
			node.name = '__lambda__'
			node.decorator_list = []
			node.body = [node.body]
			b = node.body[-1]
			node.body[-1] = ast.Return( b )
			return self.visit_FunctionDef(node)

	def visit_FunctionDef(self, node):
		global writer

		## deprecated
		#if node in self._generator_function_nodes:
		#	self._generator_functions.add( node.name )
		#	if '--native-yield' in sys.argv:
		#		raise NotImplementedError  ## TODO
		#	else:
		#		GeneratorFunctionTransformer( node, compiler=self )
		#		return

		writer.functions.append(node.name)

		is_worker_entry = False
		property_decorator = None
		decorators = []
		with_dart_decorators = []
		setter = False
		return_type = None
		return_type_keywords = {}
		fastdef = False
		javascript = False
		inline = False
		threaded = self._with_webworker
		jsfile = None

		self._typedef_vars = dict()  ## clear typed variables: filled in below by @typedef or in visit_Assign, TODO break this apart into _typed_args and _typed_locals on the node
		node._typed_args = dict()    ## used in visit class def to get types for struct

		## TODO deprecate all the glsl code
		local_typedefs = []
		typedef_chans = []
		func_expr = None

		## deprecated?
		self._func_typedefs = {}

		if writer.is_at_global_level() and not self._with_webworker:
			self._global_functions[ node.name ] = node  ## save ast-node

		for decorator in reversed(node.decorator_list):
			if isinstance(decorator, Name) and decorator.id == 'debugger':
				writer.write('@debugger')
			elif isinstance(decorator, Name) and decorator.id == 'classmethod':
				writer.write('@classmethod')
			elif isinstance(decorator, Name) and decorator.id == 'virtualoverride':
				writer.write('@virtualoverride')
			elif isinstance(decorator, Name) and decorator.id == 'extern':
				writer.write('@extern')

			elif isinstance(decorator, Call) and decorator.func.id == 'expression':
				## js function expressions are now the default, because hoisting is not pythonic.
				## when the user writes `a = def(): ...` this gets translated to `@expression( target )\n def __NAMELESS__()`
				assert len(decorator.args)==1
				func_expr = self.visit(decorator.args[0])

			elif isinstance(decorator, Call) and decorator.func.id == '__typedef__':  ## new style
				c = decorator
				assert len(c.args) == 3 and len(c.keywords)==0
				vname = self.visit(c.args[0])
				vtype = self.visit(c.args[1])
				vptr  = self.visit(c.args[2])

				self._typedef_vars[ vname ]  = vtype
				self._instances[ vname ]     = vtype
				self._func_typedefs[ vname ] = vtype
				node._typed_args[ vname ]    = vtype
				local_typedefs.append( '%s=%s' %(vname, vtype))
				writer.write('@__typedef__(%s, %s, %s)' %(vname, vtype, vptr))


			elif isinstance(decorator, Call) and decorator.func.id in ('typedef', 'typedef_chan'):  ## old style
				c = decorator
				assert len(c.args) == 0 and len(c.keywords)
				for kw in c.keywords:
					#assert isinstance( kw.value, Name)
					kwval = self.visit(kw.value)
					self._typedef_vars[ kw.arg ] = kwval
					self._instances[ kw.arg ] = kwval
					self._func_typedefs[ kw.arg ] = kwval
					node._typed_args[ kw.arg ]    = kwval
					local_typedefs.append( '%s=%s' %(kw.arg, kwval))
					if decorator.func.id=='typedef_chan':
						typedef_chans.append( kw.arg )
						writer.write('@__typedef_chan__(%s=%s)' %(kw.arg, kwval))
					else:
						writer.write('@__typedef__(%s=%s)' %(kw.arg, kwval))


			elif isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Name) and decorator.func.id == 'webworker':
				threaded = True
				assert len(decorator.args) == 1
				jsfile = decorator.args[0].s

			elif isinstance(decorator, Call) and isinstance(decorator.func, ast.Name) and decorator.func.id == 'returns':
				#if decorator.keywords:  ## deprecated
				#	for k in decorator.keywords:
				#		key = k.arg
				#		assert key == 'array' or key == 'vec4'
				#		return_type_keywords[ key ] = self.visit(k.value)
				#else:
				assert len(decorator.args) == 1
				if isinstance( decorator.args[0], Name):
					return_type = decorator.args[0].id
				elif isinstance(decorator.args[0], ast.Str):
					return_type = '"%s"' %decorator.args[0].s
				else:
					raise SyntaxError('invalid @returns argument')

			elif self._with_cpp or self._with_rust:
				writer.write('@%s' %self.visit(decorator))

			elif isinstance(decorator, Name) and decorator.id == 'fastdef':  ## TODO clean this up
				fastdef = True
				raise SyntaxError('@fast is deprecated')

			elif isinstance(decorator, Name) and decorator.id == 'javascript':
				javascript = True
				raise SyntaxError('@javascript is deprecated')

			elif isinstance(decorator, Name) and decorator.id == 'property':
				## this old style is deprecated, it worked with the old js backend and lua backend
				#property_decorator = decorator
				#n = node.name + '__getprop__'
				#self._decorator_properties[ node.original_name ] = dict( get=n, set=None )
				#node.name = n

				self._decorator_properties[ node.name ] = dict( get=decorator, set=None )
				writer.write('@getter')


			elif isinstance(decorator, Attribute) and isinstance(decorator.value, Name) and decorator.value.id in self._decorator_properties:
				if decorator.attr == 'setter':
					if self._decorator_properties[ decorator.value.id ]['set'] is not None:
						raise SyntaxError( self.format_error("decorator.setter is used more than once") )

					## old deprecated stuff
					#n = node.name + '__setprop__'
					#self._decorator_properties[ decorator.value.id ]['set'] = n
					#node.name = n
					#setter = True
					#prop_name = node.original_name

					if node.name != decorator.value.id:
						node.name = decorator.value.id

					self._decorator_properties[ decorator.value.id ]['set'] = decorator
					writer.write('@setter')

				elif decorator.attr == 'deleter':
					## javascript has no deleter for properties?
					raise NotImplementedError('TODO property deleter')
				else:
					raise SyntaxError('invalid property type')

			elif isinstance(decorator, Call) and decorator.func.id == 'custom_operator':
				assert len(decorator.args) == 1
				assert isinstance( decorator.args[0], Str )
				op = decorator.args[0].s.decode('utf-8')
				if op not in self._custom_operators:
					raise RuntimeError( op, self._custom_operators )
				self._custom_operators[ op ] = node.name

			else:
				decorators.append( decorator )


		if threaded:
			if not jsfile: jsfile = 'worker.js'
			#writer_main.write('%s = "%s"' %(node.name, jsfile))
			self._webworker_functions[ node.name ] = jsfile
			writer = get_webworker_writer( jsfile )  ## updates global `writer`



		## force python variable scope, and pass user type information to second stage of translation.
		## the dart backend can use this extra type information for speed and debugging.
		## the Go and GLSL backends require this extra type information.
		vars = []
		local_typedef_names = set()
		if not self._with_coffee:
			try:
				local_vars, global_vars = retrieve_vars(node.body)
			except SyntaxError as err:
				raise SyntaxError( self.format_error(err) )

			local_vars = local_vars-global_vars
			inlined_long = False
			if local_vars:
				args_typedefs = []
				args = [ a.id for a in node.args.args ]

				for v in local_vars:
					usertype = None
					if '=' in v:
						t,n = v.split('=')  ## unpack type and name
						v = '%s=%s' %(n,t)  ## reverse
						local_typedef_names.add( n )
						if t == 'long' and inlined_long == False:
							inlined_long = True
							writer.write('''inline("if (__NODEJS__==true) var long = require('long')")''')  ## this is ugly

						if n in args:
							args_typedefs.append( v )
						else:
							local_typedefs.append( v )
					elif v in args or v in local_typedef_names: pass
					else: vars.append( v )

				if args_typedefs:
					writer.write('@__typedef__(%s)' %','.join(args_typedefs))


		if func_expr:
			writer.write('@expression(%s)' %func_expr)


		if not self._with_js and not javascript:
			writer.write('@__pyfunction__')

		if return_type or return_type_keywords:
			if return_type_keywords and return_type:
				kw = ['%s=%s' %(k,v) for k,v in return_type_keywords.items()]
				writer.write('@returns(%s, %s)' %(return_type,','.join(kw)) )
			elif return_type_keywords:
				writer.write('@returns(%s)' %','.join( ['%s=%s' %(k,v) for k,v in return_type_keywords.items()] ))
			else:
				writer.write('@returns(%s)' %return_type)

		## apply decorators ##
		for decorator in decorators:
			writer.write('@%s' %self.visit(decorator))


		if self._with_go or self._with_rust or self._with_cpp:  ## pass-thru unchanged to next stage
			args = []
			offset = len(node.args.args) - len(node.args.defaults)
			for i, arg in enumerate(node.args.args):
				a = arg.id
				dindex = i - offset
				if dindex >= 0 and node.args.defaults:
					## try to infer type from named param default,
					## this way the user can simply write `def f(a=0)`
					## rather than `def f(a:int=0)`
					default_node = node.args.defaults[dindex]
					if a not in node._typed_args:
						if isinstance(default_node, ast.Num):
							if str(default_node.n).isdigit():
								node._typed_args[a] = 'int'
							else:
								node._typed_args[a] = 'float'  ## default to 32 or 64 bit float?
							writer.write('@__typedef__(%s="%s")' %(a, node._typed_args[a]))
						elif isinstance(default_node, ast.Str):
							node._typed_args[a] = 'string'
							writer.write('@__typedef__(%s="%s")' %(a, node._typed_args[a]))

					default = self.visit(default_node)
					args.append( '%s=%s' %(a, default))
				else:
					args.append( a )

			if node.args.vararg: args.append( '*%s' %node.args.vararg )
			writer.write( 'def %s( %s ):' % (node.name, ','.join(args)) )


		elif self._with_js or javascript or self._with_ll:

			kwargs_name = node.args.kwarg or '_kwargs_'

			args = []
			offset = len(node.args.args) - len(node.args.defaults)
			for i, arg in enumerate(node.args.args):
				a = arg.id
				dindex = i - offset
				if dindex >= 0 and node.args.defaults:
					pass
				else:
					args.append( a )

			if node.args.vararg:
				if len(node.args.defaults) or node.args.kwarg:
					if args:
						writer.write( 'def %s( %s, %s, *%s ):' % (node.name, ','.join(args), kwargs_name, node.args.vararg))
					else:
						writer.write( 'def %s( %s, *%s ):' % (node.name, kwargs_name, node.args.vararg))
				elif args:
					writer.write( 'def %s( %s, *%s ):' % (node.name, ','.join(args), node.args.vararg))
				else:
					writer.write( 'def %s( *%s ):' % (node.name, node.args.vararg))
			elif len(node.args.defaults) or node.args.kwarg:
				if args:
					writer.write( 'def %s( %s, %s ):' % (node.name, ','.join(args), kwargs_name ) )
				else:
					writer.write( 'def %s( %s ):' % (node.name, kwargs_name) )
			else:
				writer.write( 'def %s( %s ):' % (node.name, ','.join(args)) )

		else:
			if len(node.args.defaults) or node.args.kwarg or len(node.args.args) or node.args.vararg:
				writer.write('def %s(args, kwargs):' % node.name)
			else:
				writer.write('def %s():' % node.name)

		writer.push()

		## write local typedefs and var scope ##
		a = ','.join( vars )
		if local_typedefs:
			if a: a += ','
			a += ','.join(local_typedefs)
		writer.write('var(%s)' %a)

		#####################################################################
		if self._with_go or self._with_rust or self._with_cpp:
			pass

		elif (self._with_js or javascript or self._with_ll):
			if node.args.defaults:
				if not self._fast_js:
					## this trys to recover when called in a bad way,
					## however, this could be dangerous because the program
					## should fail if a function is called this badly.
					kwargs_name = node.args.kwarg or '_kwargs_'
					lines = [ 'if (!( %s instanceof Object )) {' %kwargs_name ]
					a = ','.join( ['%s: arguments[%s]' %(arg.id, i) for i,arg in enumerate(node.args.args)] )
					lines.append( 'var %s = {%s}' %(kwargs_name, a))
					lines.append( '}')
					for a in lines:
						writer.write("inline('''%s''')" %a)

				offset = len(node.args.args) - len(node.args.defaults)

				maxlen = 0
				maxlen2 = 0
				for i, arg in enumerate(node.args.args):
					dindex = i - offset
					if dindex >= 0:
						dval = self.visit( node.args.defaults[dindex] )

						if len(arg.id) > maxlen:
							maxlen = len(arg.id)

						if len(dval) > maxlen2:
							maxlen2 = len(dval)


				for i, arg in enumerate(node.args.args):
					dindex = i - offset
					if dindex >= 0:
						default_value = self.visit( node.args.defaults[dindex] )
						#a = (kwargs_name, kwargs_name, arg.id, arg.id, default_value, arg.id, kwargs_name, arg.id)
						#b = "if (%s === undefined || %s.%s === undefined) {var %s = %s} else {var %s=%s.%s}" %a
						spaces = ' ' * (maxlen - len(arg.id))
						spaces2 = ' ' * (maxlen2 - len(default_value))

						## this is fast, but fails in the case where the user has called a function that takes
						## named keyword args, and called it without giving those keyword names. This case can
						## easily popup when the user has refactored the function to use named keyword args,
						## but did not update all code that calls that function.
						#a = (arg.id, spaces, kwargs_name, kwargs_name,arg.id, spaces, default_value, spaces2, kwargs_name, arg.id)
						#b = "var %s %s= (%s === undefined || %s.%s === undefined)%s?\t%s %s: %s.%s" %a

						## new version throws a runtime error if the function was called improperly.
						ERR = 'function `%s` requires named keyword arguments, invalid parameter for `%s`' %(node.name, arg.id)
						a = (arg.id, spaces, kwargs_name, kwargs_name, kwargs_name,arg.id, spaces, default_value, spaces2, kwargs_name, kwargs_name, arg.id,ERR)
						b = "var %s %s= (%s===undefined || (typeof(%s)=='object' && %s.%s===undefined))%s?\t%s %s:   typeof(%s)=='object'?%s.%s: __invalid_call__('%s',arguments)" %a

						c = "inline('''%s''')" %b
						writer.write( c )


		################# function body #################


		if threaded and is_worker_entry:  ## DEPRECATED - TODO REMOVE
			for i,arg in enumerate(node.args.args):
				writer.write( '%s = __webworker_wrap(%s, %s)' %(arg.id, arg.id, i))
				writer.write('__wargs__.push(%s)'%arg.id)


		self._return_type = None # tries to catch a return type in visit_Return

		## write function body ##
		## if sleep() is called or a new webworker is started, the following function body must be wrapped in
		## a closure callback and called later by setTimeout
		timeouts = []
		#continues = []
		for b in node.body:

			if self._use_threading and isinstance(b, ast.Assign) and isinstance(b.value, ast.Call):  ## DEPRECATED - TODO REMOVE
				if isinstance(b.value.func, ast.Attribute) and isinstance(b.value.func.value, Name) and b.value.func.value.id == 'threading':
					if b.value.func.attr == 'start_new_thread':
						self.visit(b)
						writer.write('__run__ = True')
						writer.write('def __callback%s():' %len(timeouts))
						writer.push()
						## workerjs for nodejs requires at least 100ms to initalize onmessage/postMessage
						timeouts.append(0.2)
						continue
					elif b.value.func.attr == 'start_webworker':
						self.visit(b)
						writer.write('__run__ = True')
						writer.write('def __callback%s():' %len(timeouts))
						writer.push()
						## workerjs for nodejs requires at least 100ms to initalize onmessage/postMessage
						timeouts.append(0.2)
						continue

				elif self._with_webworker and isinstance(b, ast.Assign) and isinstance(b.value, ast.Call) and isinstance(b.value.func, ast.Name) and b.value.func.id in self._global_functions:
					#assert b.value.calling_from_worker
					#raise SyntaxError(b)
					self.visit(b)
					writer.write('def __blocking( %s ):' %self.visit(b.targets[0]))
					writer.push()
					timeouts.append('BLOCKING')
					continue


			elif self._use_sleep:
				c = b
				if isinstance(b, ast.Expr):
					b = b.value

				if isinstance(b, ast.Call) and isinstance(b.func, ast.Name) and b.func.id == 'sleep':
					writer.write('__run__ = True')
					writer.write('def __callback%s():' %len(timeouts))
					writer.push()
					timeouts.append( self.visit(b.args[0]) )
					continue

				elif isinstance(b, ast.While):  ## TODO
					has_sleep = False
					for bb in b.body:
						if isinstance(bb, ast.Expr):
							bb = bb.value
						if isinstance(bb, ast.Call) and isinstance(bb.func, ast.Name) and bb.func.id == 'sleep':
							has_sleep = float(self.visit(bb.args[0]))

					if has_sleep > 0.0:
						has_sleep = int(has_sleep*1000)
						#writer.write('__run_while__ = True')
						writer.write('__continue__ = True')
						writer.write('def __while():')
						writer.push()

						for bb in b.body:
							if isinstance(bb, ast.Expr):
								bb = bb.value
							if isinstance(bb, ast.Call) and isinstance(bb.func, ast.Name) and bb.func.id == 'sleep':
								continue
								#TODO - split body and generate new callback - now sleep is only valid at the end of the while loop

							else:
								e = self.visit(bb)
								if e: writer.write( e )

						writer.write( 'if %s: __run_while__ = True' %self.visit(b.test))
						writer.write( 'else: __run_while__ = False')

						writer.write('if __run_while__: setTimeout(__while, %s)' %(has_sleep))
						writer.write('elif __continue__: setTimeout(__callback%s, 0)' %len(timeouts))

						writer.pull()

						writer.write('setTimeout(__while, 0)')
						writer.write('__run__ = True')
						writer.write('def __callback%s():' %len(timeouts))
						writer.push()
						timeouts.append(None)
						continue

					else:
						self.visit(b)

					continue

				b = c  ## replace orig b

			self.visit(b)

		i = len(timeouts)-1
		while timeouts:
			ms = timeouts.pop()
			if ms == 'BLOCKING':
				writer.write(	'threading._blocking_callback = None')
				writer.pull()
				writer.write('threading._blocking_callback = __blocking')
			elif ms is not None:
				writer.pull()

				ms = float(ms)
				ms *= 1000
				writer.write('if __run__: setTimeout(__callback%s, %s)' %(i, ms))
				writer.write('elif __continue__: setTimeout(__callback%s, %s)' %(i+1, ms))
			i -= 1

		if self._return_type:       ## check if a return type was caught
			if return_type:
				assert return_type == self._return_type
			else:
				return_type = self._return_type
			self._function_return_types[ node.name ] = self._return_type
		self._return_type = None


		############################################################
		### DEPRECATED
		if setter and 'set' in self._injector:  ## inject extra code
			value_name = node.args.args[1].id
			inject = [
				'if self.property_callbacks["%s"]:' %prop_name,
				'self.property_callbacks["%s"](["%s", %s, self], JSObject())' %(prop_name, prop_name, value_name)
			]
			writer.write( ' '.join(inject) )

		elif self._injector and node.original_name == '__init__':
			if 'set' in self._injector:
				writer.write( 'self.property_callbacks = JSObject()' )
			if 'init' in self._injector:
				writer.write('if self.__class__.init_callbacks.length:')
				writer.push()
				writer.write('for callback in self.__class__.init_callbacks:')
				writer.push()
				writer.write('callback( [self], JSObject() )')
				writer.pull()
				writer.pull()
		############################################################

		writer.pull()  ## end function body

		self._typedef_vars = dict()  ## clear typed variables

		if self._in_js_class:  ## used when making multiple output javascripts, like main.js and webworker.js
			#writer = writer_main
			return


		types = []
		for x in zip(node.args.args[-len(node.args.defaults):], node.args.defaults):
			key = x[0]
			value = x[1]
			if isinstance(value, ast.Name):
				value = value.id
			else:
				value = type(value).__name__.lower()
			types.append( '%s : "%s"' %(self.visit(key), value) )


		if self._introspective_functions:
			## note, in javascript function.name is a non-standard readonly attribute,
			## the compiler creates anonymous functions with name set to an empty string.
			writer.write('%s.NAME = "%s"' %(node.name,node.name))

			writer.write( '%s.args_signature = [%s]' %(node.name, ','.join(['"%s"'%n.id for n in node.args.args])) )
			defaults = ['%s:%s'%(self.visit(x[0]), self.visit(x[1])) for x in zip(node.args.args[-len(node.args.defaults):], node.args.defaults) ]
			writer.write( '%s.kwargs_signature = {%s}' %(node.name, ','.join(defaults)) )
			writer.write( '%s.types_signature = {%s}' %(node.name, ','.join(types)) )

			if return_type:
				writer.write('%s.return_type = "%s"'%(node.name, return_type))



	#################### loops ###################
	## the old-style for loop that puts a while loop inside a try/except and catches StopIteration,
	## has a problem because at runtime if there is an error inside the loop, it will not show up in a strack trace,
	## the error is slient.  FAST_FOR is safer and faster, although it is not strictly Python because in standard
	## Python a list is allowed to grow or string while looping over it.  FAST_FOR only deals with a fixed size thing to loop over.
	FAST_FOR = True

	def visit_Continue(self, node):
		if self._with_js:
			writer.write('continue')
		else:
			writer.write('continue')
		return ''

	def visit_Break(self, node):
		if self._in_loop_with_else:
			writer.write('__break__ = True')
		writer.write('break')

	def visit_For(self, node):
		if node.orelse:
			raise SyntaxError( self.format_error('the syntax for/else is deprecated') )


		if self._with_go:
			writer.write( 'for %s in %s:' %(self.visit(node.target), self.visit(node.iter)) )
			writer.push()
			map(self.visit, node.body)
			writer.pull()
			return None

		if self._with_rpc_name and isinstance(node.iter, ast.Attribute) and isinstance(node.iter.value, ast.Name) and node.iter.value.id == self._with_rpc_name:
			target = self.visit(node.target)
			writer.write('def __rpc_loop__():')
			writer.push()
			writer.write(	'%s = __rpc_iter__(%s, "%s")' %(target, self._with_rpc, node.iter.attr) )
			writer.write(	'if %s == "__STOP_ITERATION__": __continue__()' %target)
			writer.write(	'else:')
			writer.push()
			map( 				self.visit, node.body )
			writer.write(		'__rpc_loop__()')
			writer.pull()
			writer.pull()
			writer.write('__rpc_loop__()')

			writer.write('def __continue__():')  ## because this def comes after, it needs to be `hoisted` up by the javascript VM
			writer.push()
			return None


		iterid = self._iter_ids
		self._iter_ids += 1

		target = node.target
		enumtar = None
		if isinstance(node.iter, ast.Call) and isinstance(node.iter.func, Name) and node.iter.func.id == 'enumerate':
			iter = node.iter.args[0]
			if isinstance(target, ast.Tuple):
				enumtar = target.elts[0]
				target = target.elts[1]
			else:
				raise SyntaxError('for enumerate loop, requires unpacking to a: index,value pair')
		else:
			iter = node.iter

		if enumtar:
			writer.write('var(%s)'%enumtar.id)
			writer.write('%s = 0' %enumtar.id)

		vars = []
		multi_target = []

		if isinstance(target, ast.Tuple):
			vars.append( '__mtarget__%s' %iterid)
			for elt in target.elts:
				if isinstance(elt, ast.Name):
					multi_target.append( elt.id )
					vars.append( elt.id )
				else:
					raise NotImplementedError('unknown iterator sub-target type: %s'%target)
		elif isinstance(target, ast.Name):
			vars.append( target.id )
		else:
			raise NotImplementedError('unknown iterator target type: %s'%target)


		if self._with_ll or self._with_cpp or self._with_rust or self._with_go:
			writer.write('for %s in %s:' %(self.visit(target), self.visit(iter)))
			writer.push()
			map(self.visit, node.body)
			writer.pull()

		elif self._with_js:
			if isinstance(iter, ast.Call) and isinstance(iter.func, Name) and iter.func.id in ('range','xrange'):
				iter_start = '0'
				if len(iter.args) == 2:
					iter_start = self.visit(iter.args[0])
					iter_end = self.visit(iter.args[1])
				else:
					iter_end = self.visit(iter.args[0])

				iter_name = target.id

				writer.write('inline("/*for var in range*/")')

				writer.write('var(%s)' %iter_name)
				if iter_start == '0':
					writer.write('%s = -1' %iter_name)
				else:
					writer.write('%s = %s-1' %(iter_name, iter_start))
				if '(' in iter_end:  ## if its a function call, cache it to a variable
					writer.write('var(%s__end__)' %iter_name)
					writer.write('%s__end__ = %s' %(iter_name, iter_end))
					writer.write('while inline("++%s") < %s__end__:' %(iter_name, iter_name))
				else:
					writer.write('while inline("++%s") < %s:' %(iter_name, iter_end))

				writer.push()
				map(self.visit, node.body)

				if self._with_js:
					#writer.write('inline("%s += 1")' %iter_name )
					if enumtar:
						writer.write('inline("%s += 1")'%enumtar.id)
				else:
					#writer.write('%s += 1' %iter_name )
					if enumtar:
						writer.write('%s += 1'%enumtar.id)

				writer.pull()

			elif isinstance(iter, ast.Call) and isinstance(iter.func, Name) and iter.func.id in self._generator_functions:
				iter_name = self.visit(target)
				writer.write('var(%s, __generator__%s)' %(iter_name,iterid))
				writer.write('__generator__%s = %s' %(iterid,self.visit(iter)))
				writer.write('while __generator__%s.__done__ != 1:'%iterid)
				writer.push()
				writer.write('%s = __generator__%s.next()'%(iter_name,iterid))
				map(self.visit, node.body)
				writer.pull()

			else:
				if multi_target:
					writer.write('var(%s)' % ','.join(vars))
					writer.write('for __mtarget__%s in %s:' %(iterid,self.visit(iter)))
					writer.push()
					for i,elt in enumerate(multi_target):
						writer.write('%s = __mtarget__%s[%s]' %(elt,iterid,i))

				else:
					a = self.visit(target)
					self._in_assign_target = True
					b = self.visit(iter)
					self._in_assign_target = False
					writer.write('for %s in %s:' %(a, b))
					writer.push()


				map(self.visit, node.body)

				if enumtar:
					writer.write('%s += 1'%enumtar.id)

				writer.pull()
		else:

			## TODO else remove node.target.id from self._instances
			if isinstance(iter, Name) and iter.id in self._global_typed_lists:
				self._instances[ target.id ] = list( self._global_typed_lists[ iter.id ] )[0]


			vars.append('__iterator__%s'%iterid)
			if not self._with_coffee:
				writer.write('var(%s)' % ','.join(vars))


			is_range = False
			is_generator = False
			iter_start = '0'
			iter_end = None
			if self.FAST_FOR and isinstance(iter, ast.Call) and isinstance(iter.func, Name) and iter.func.id in ('range','xrange'):
				is_range = True
				if len(iter.args) == 2:
					iter_start = self.visit(iter.args[0])
					iter_end = self.visit(iter.args[1])
				else:
					iter_end = self.visit(iter.args[0])

			elif isinstance(iter, ast.Call) and isinstance(iter.func, Name) and iter.func.id in self._generator_functions:
				is_generator = True
			else:
				if hasattr(node, 'lineno'):
					src = self._source[ node.lineno-1 ]
					src = src.replace('"', '\\"')
					err = 'no iterator - line %s: %s'	%(node.lineno, src.strip())
					writer.write('__iterator__%s = __get__(__get__(%s, "__iter__", "%s"), "__call__")([], __NULL_OBJECT__)' %(iterid, self.visit(iter), err))

				else:
					writer.write('__iterator__%s = __get__(__get__(%s, "__iter__"), "__call__")([], __NULL_OBJECT__)' %(iterid, self.visit(iter)))

			if is_generator:
				iter_name = self.visit(target)
				if not self._with_coffee:
					writer.write('var(%s, __generator__%s)' %(iter_name, iterid))
				writer.write('__generator__%s = %s' %(iterid,self.visit(iter)))
				writer.write('while __generator__%s.__done__ != 1:'%iterid)
				writer.push()
				writer.write('%s = __generator__%s.next()'%(iter_name,iterid))
				map(self.visit, node.body)
				writer.pull()


			elif is_range:
				iter_name = target.id
				if not self._with_coffee:
					writer.write('var(%s, %s__end__)' %(iter_name, iter_name))
				writer.write('%s = %s' %(iter_name, iter_start))
				writer.write('%s__end__ = %s' %(iter_name, iter_end))   ## assign to a temp variable.
				#writer.write('while %s < %s:' %(iter_name, iter_end))  ## this fails with the ternary __add_op
				writer.write('while %s < %s__end__:' %(iter_name, iter_name))

				writer.push()
				map(self.visit, node.body)
				writer.write('%s += 1' %iter_name )

				if enumtar:
					writer.write('%s += 1'%enumtar.id)

				writer.pull()
			else:
				if not self._with_coffee:
					writer.write('var(__next__%s)'%iterid)
				writer.write('__next__%s = __get__(__iterator__%s, "next")'%(iterid,iterid))
				writer.write('while __iterator__%s.index < __iterator__%s.length:'%(iterid,iterid))

				writer.push()

				if multi_target:
					writer.write('__mtarget__%s = __next__%s()'%(iterid, iterid))
					for i,elt in enumerate(multi_target):
						writer.write('%s = __mtarget__%s[%s]' %(elt,iterid,i))
				else:
					writer.write('%s = __next__%s()' %(target.id, iterid))

				map(self.visit, node.body)

				if enumtar:
					writer.write('%s += 1'%enumtar.id)

				writer.pull()
	
			return ''

	_call_ids = 0
	def visit_While(self, node):
		if self._cache_while_body_calls:  ## TODO add option for this
			for n in node.body:
				calls = collect_calls(n)
				for c in calls:
					if isinstance(c.func, ast.Name):  ## these are constant for sure
						i = self._call_ids
						writer.write( '__call__%s = __get__(%s,"__call__")' %(i,self.visit(c.func)) )
						c.func.id = '__call__%s'%i
						c.constant = True
						self._call_ids += 1

		if node.orelse:
			raise SyntaxError( self.format_error('while/else loop is not allowed') )
			self._in_loop_with_else = True
			writer.write('var(__break__)')
			writer.write('__break__ = False')

		self._in_while_test = True
		writer.write('while %s:' % self.visit(node.test))
		self._in_while_test = False
		writer.push()
		map(self.visit, node.body)
		writer.pull()

		if node.orelse:
			self._in_loop_with_else = False
			writer.write('if __break__ == False:')
			writer.push()
			map(self.visit, node.orelse)
			writer.pull()

	def visit_With(self, node):
		global writer

		if isinstance( node.context_expr, ast.Call ) and isinstance(node.context_expr.func, ast.Name) and node.context_expr.func.id == 'rpc':
			self._with_rpc = self.visit( node.context_expr.args[0] )
			if isinstance(node.optional_vars, ast.Name):
				self._with_rpc_name = node.optional_vars.id
			for b in node.body:
				a = self.visit(b)
				if a: writer.write(a)
			self._with_rpc = None
			self._with_rpc_name = None

		elif isinstance( node.context_expr, Name ) and node.context_expr.id == 'webworker':
			self._with_webworker = True
			writer = get_webworker_writer( 'worker.js' )

			#writer.write('if typeof(require) != "undefined": requirejs = require')  ## compatible with nodewebkit
			#writer.write('else: importScripts("require.js")')

			for b in node.body:
				a = self.visit(b)
				if a: writer.write(a)
			self._with_webworker = False
			writer = writer_main

		elif isinstance( node.context_expr, Name ) and node.context_expr.id == 'lowlevel':
			self._with_ll = True
			#map(self.visit, node.body)
			for b in node.body:
				a = self.visit(b)
				if a: writer.write(a)
			self._with_ll = False

		elif isinstance( node.context_expr, Name ) and node.context_expr.id == 'javascript':  ## deprecated
			raise RuntimeError('with javascript deprecated')
		elif isinstance( node.context_expr, Name ) and node.context_expr.id == 'python':  ## deprecated
			raise RuntimeError('with python deprecated')

		elif isinstance( node.context_expr, Name ) and node.context_expr.id == 'fastdef':
			raise RuntimeError('with fastdef deprecated')

		elif isinstance( node.context_expr, Name ) and node.context_expr.id == 'static':
			raise RuntimeError('with static: is deprecated')

		elif isinstance( node.context_expr, Name ) and node.context_expr.id in EXTRA_WITH_TYPES:
			writer.write('with %s:' %self.visit(node.context_expr))
			writer.push()
			for b in node.body:
				a = self.visit(b)
				if a: writer.write(a)
			writer.pull()

		elif isinstance( node.context_expr, ast.Call ) and isinstance(node.context_expr.func, ast.Name) and node.context_expr.func.id in EXTRA_WITH_TYPES:
			if node.context_expr.keywords:
				assert len(node.context_expr.keywords)==1
				k = node.context_expr.keywords[0].arg
				v = self.visit(node.context_expr.keywords[0].value)
				a = 'with %s(%s=%s):' %( self.visit(node.context_expr.func), k,v )
				writer.write(a)
			else:
				writer.write('with %s:' %self.visit(node.context_expr))

			writer.push()
			for b in node.body:
				a = self.visit(b)
				if a: writer.write(a)
			writer.pull()

		elif isinstance( node.context_expr, ast.Call ) and isinstance(node.context_expr.func, ast.Name) and node.context_expr.func.id == 'asm':
			asmcode = []
			for b in node.body:
				asmcode.append( b.value.s )
			args = [ 'code="%s"' % ''.join(asmcode) ]
			for kw in node.context_expr.keywords:
				args.append( '%s=%s' %(kw.arg, self.visit(kw.value)) )
			asm = '__asm__( %s )' %(','.join(args))
			writer.write( asm )
		elif isinstance( node.context_expr, ast.Call ) and isinstance(node.context_expr.func, ast.Name) and node.context_expr.func.id == 'extern':
			writer.write('with %s:' %self.visit(node.context_expr))
			writer.push()
			for b in node.body:
				a = self.visit(b)
				if a: writer.write(a)
			writer.pull()
		elif isinstance( node.context_expr, ast.Str):
			writer.write('with %s:' %self.visit(node.context_expr))
			writer.push()
			for b in node.body:
				a = self.visit(b)
				if a: writer.write(a)
			writer.pull()

		elif isinstance(node.context_expr, ast.Name) and node.context_expr.id=='syntax':
			if isinstance(node.optional_vars, ast.Name):
				writer.write('with syntax(%s):' %self._autotyped_dicts[node.optional_vars.id])
			else:
				writer.write('with syntax(%s):' %self.visit(node.optional_vars))
			writer.push()
			for b in node.body:
				a = self.visit(b)
				if a: writer.write(a)
			writer.pull()

		elif isinstance( node.context_expr, ast.Call ) and isinstance(node.context_expr.func, ast.Name) and node.context_expr.func.id == 'syntax':
			writer.write('with %s:' %self.visit(node.context_expr))
			writer.push()
			for b in node.body:
				a = self.visit(b)
				if a: writer.write(a)
			writer.pull()

		elif isinstance( node.context_expr, ast.Call ) and isinstance(node.context_expr.func, ast.Name) and node.context_expr.func.id == 'timeout':
			writer.write('with %s:' %self.visit(node.context_expr))
			writer.push()
			for b in node.body:
				a = self.visit(b)
				if a: writer.write(a)
			writer.pull()


		elif isinstance(node.context_expr, ast.Name) or isinstance(node.context_expr, ast.Tuple):  ## assume that backend can support this
			#if isinstance(node.optional_vars, ast.Subscript) and isinstance(node.optional_vars.slice, ast.Index):
			if node.optional_vars:
				writer.write('with %s as %s:' %(self.visit(node.context_expr), self.visit(node.optional_vars)))
			else:
				writer.write('with %s:' %self.visit(node.context_expr))

			writer.push()
			for b in node.body:
				a = self.visit(b)
				if a: writer.write(a)
			writer.pull()

		else:
			raise SyntaxError('invalid use of "with" statement: %s' %self.visit(node.context_expr))

EXTRA_WITH_TYPES = ('__switch__', '__default__', '__case__', '__select__')





class CollectCalls(NodeVisitor):
	_calls_ = []
	def visit_Call(self, node):
		self._calls_.append( node )

def collect_calls(node):
	CollectCalls._calls_ = calls = []
	CollectCalls().visit( node )
	return calls


class CollectDictComprehensions(NodeVisitor):
	_comps_ = []
	def visit_GeneratorExp(self,node):
		self._comps_.append( node )
		self.visit( node.elt )
		for gen in node.generators:
			self.visit( gen.iter )
			self.visit( gen.target )
	def visit_DictComp(self, node):
		self._comps_.append( node )
		self.visit( node.key )
		self.visit( node.value )
		for gen in node.generators:
			self.visit( gen.iter )
			self.visit( gen.target )

def collect_dict_comprehensions(node):
	CollectDictComprehensions._comps_ = comps = []
	CollectDictComprehensions().visit( node )
	return comps


class CollectComprehensions(NodeVisitor):
	_comps_ = []
	def visit_GeneratorExp(self,node):
		self._comps_.append( node )
		self.visit( node.elt )
		for gen in node.generators:
			self.visit( gen.iter )
			self.visit( gen.target )
	def visit_ListComp(self, node):
		self._comps_.append( node )
		self.visit( node.elt )
		for gen in node.generators:
			self.visit( gen.iter )
			self.visit( gen.target )

def collect_comprehensions(node):
	CollectComprehensions._comps_ = comps = []
	CollectComprehensions().visit( node )
	return comps

class CollectGenFuncs(NodeVisitor):
	_funcs = []
	_genfuncs = []
	def visit_FunctionDef(self, node):
		self._funcs.append( node )
		node._yields = []
		node._loops = []
		for b in node.body:
			self.visit(b)
		self._funcs.pop()

	def visit_Yield(self, node):
		func = self._funcs[-1]
		func._yields.append( node )
		if func not in self._genfuncs:
			self._genfuncs.append( func )

	def visit_For(self, node):
		if len(self._funcs):
			self._funcs[-1]._loops.append( node )
		for b in node.body:
			self.visit(b)

	def visit_While(self, node):
		if len(self._funcs):
			self._funcs[-1]._loops.append( node )
		for b in node.body:
			self.visit(b)


def collect_generator_functions(node):
	CollectGenFuncs._funcs = []
	CollectGenFuncs._genfuncs = gfuncs = []
	CollectGenFuncs().visit( node )
	return gfuncs



def python_to_pythonjs(script, **kwargs):
	translator = PythonToPythonJS(
		source = script,
		**kwargs
	)

	code = writer.getvalue()

	if translator.has_webworkers():
		userimports = ['"%s"'%imp for imp in translator.get_webworker_imports()]
		pre = [
			'__workerimports__ = [%s]' %','.join(userimports),
			#'__workerpool__ = new(__WorkerPool__(__workersrc__, __workerimports__))',
			'inline("var ⲢⲑⲑⲒ = new __WorkerPool__(__workersrc__, __workerimports__)")',
			''
		]
		code = '\n'.join(pre) + code
		res = {'main':code}
		for jsfile in translator.get_webworker_file_names():
			res[ jsfile ] = get_webworker_writer( jsfile ).getvalue()
		return res
	else:
		if '--debug' in sys.argv:
			try:
				open('/tmp/python-to-pythonjs.debug.py', 'wb').write(code)
			except:
				pass
		return code

```