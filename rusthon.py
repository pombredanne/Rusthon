#!/usr/bin/env python
__version__ = '0.9.9'
import os, sys, subprocess, hashlib
#import pythonjs
#import pythonjs.pythonjs
#import pythonjs.python_to_pythonjs
#import pythonjs.pythonjs_to_cpp
#import pythonjs.pythonjs_to_verilog
#import pythonjs.typedpython as typedpython
import tempfile


def compile_js( script, module_path, main_name='main', directjs=False, directloops=False ):
	'''
	directjs = False     ## compatible with pythonjs-minimal.js
	directloops = False  ## allows for looping over strings, arrays, hmtlElements, etc. if true outputs cleaner code.
	'''
	fastjs = True  ## this is now the default, and complete python mode is deprecated
	result = {}

	pyjs = python_to_pythonjs(
		script,
		module_path=module_path,
		fast_javascript = fastjs,
		pure_javascript = directjs
	)

	if isinstance(pyjs, dict):  ## split apart by webworkers
		for jsfile in a:
			result[ jsfile ] = translate_to_javascript(
				a[jsfile],
				webworker=jsfile != 'main',
				requirejs=False,
				insert_runtime=False,
				fast_javascript = fastjs,
				fast_loops      = directloops
			)

	else:

		code = translate_to_javascript(
			pyjs,
			requirejs=False,
			insert_runtime=False,
			fast_javascript = fastjs,
			fast_loops      = directloops
		)
		if isinstance(code, dict):
			result.update( code )
		else:
			result['main'] = code

	if main_name != 'main':
		#assert main_name.endswith('.js')  ## allow tag names
		result[main_name] = result.pop('main')

	return result

def compile_java( javafiles ):
	assert 'JAVA_HOME' in os.environ
	tmpdir  = tempfile.gettempdir()
	cmd = ['javac']
	cmd.extend( javafiles )
	print(' '.join(cmd))
	subprocess.check_call(cmd, cwd=tmpdir)
	classfiles = [jfile.replace('.java', '.class') for jfile in javafiles]
	cmd = ['jar', 'cvf', 'mybuild.jar']
	cmd.extend( classfiles )
	print(' '.join(cmd))
	subprocess.check_call(cmd, cwd=tmpdir)
	jarfile = os.path.join(tmpdir,'mybuild.jar')
	assert os.path.isfile(jarfile)
	return {'class-files':classfiles, 'jar':jarfile}


def compile_giws_bindings( xml ):
	tmpdir  = tempfile.gettempdir()
	tmpfile = os.path.join(tmpdir, 'rusthon_giws.xml')
	open(tmpfile, 'wb').write(xml)
	cmd = [
		'giws',
		'--description-file='+tmpfile,
		'--output-dir='+tmpdir,
		#'--per-package',
		'--disable-return-size-array',
		#'--throws-exception-on-error', # requires GiwsException.hxx and GiwsException.cpp
	]
	#subprocess.check_call(cmd)
	proc = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
	proc.wait()
	if proc.returncode:
		raise RuntimeError(proc.stderr.read())
	else:
		headers = []
		impls = []
		for line in proc.stdout.read().splitlines():
			if line.endswith(' generated ...'):  ## TODO something better
				name = line.split()[0]
				if name.endswith('.hxx'):
					headers.append( name )
				elif name.endswith('.cpp'):
					impls.append( name )

		code = []
		for header in headers:
			data = open(os.path.join(tmpdir,header), 'rb').read()
			code.append( data )

		for impl in impls:
			data = open(os.path.join(tmpdir,impl), 'rb').read()
			lines = ['/* %s */' %impl]
			includes = []  ## ignore these
			for line in data.splitlines():
				if line.startswith('#include'):
					includes.append(line)
				else:
					lines.append(line)
			code.append( '\n'.join(lines) )

		return '\n'.join(code)

def java_to_rusthon( input ):
	j2pybin = 'j2py'
	if os.path.isfile(os.path.expanduser('~/java2python/bin/j2py')):
		j2pybin = os.path.expanduser('~/java2python/bin/j2py')
	print('======== %s : translate to rusthon' %j2pybin)
	j2py = subprocess.Popen([j2pybin, '--rusthon'], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
	stdout,stderr  = j2py.communicate( input )
	if stderr: raise RuntimeError(stderr)
	if j2py.returncode: raise RuntimeError('j2py error!')
	print(stdout)
	print('---------------------------------')
	rcode = typedpython.transform_source(stdout.replace('    ', '\t'))
	print(rcode)
	print('---------------------------------')
	return rcode




def new_module():
	return {
		'markdown': '',
		'python'  : [],
		'rusthon' : [],
		'rust'    : [],
		'c'       : [],
		'c++'     : [],
		'c#'      : [],
		'go'      : [],
		'html'    : [],
		'verilog' : [],
		'bash'    : [],
		'java'    : [],
		'nim'     : [],
		'xml'     : [],
		'json'    : [],
		'rapydscript':[],
		'javascript':[],
	}

def import_md( url, modules=None, index_offset=0 ):
	assert modules is not None
	doc = []
	code = []
	code_links = []
	code_idirs = []
	code_defines = []
	lang = False
	in_code = False
	index = 0
	prevline = None
	tag = None
	fences = 0
	base_path, markdown_name = os.path.split(url)
	data = open(url, 'rb').read()

	for line in data.splitlines():
		if line.startswith('* @link:'):
			code_links.append( os.path.expanduser(line.split(':')[-1]) )
		elif line.startswith('* @include:'):
			code_idirs.append( os.path.expanduser(line.split(':')[-1]) )
		elif line.startswith('* @define:'):
			code_defines.extend( line.split(':')[-1].strip().split() )
		# Start or end of a code block.
		elif line.strip().startswith('```'):
			fences += 1
			# End of a code block.
			if in_code:
				if lang:
					p, n = os.path.split(url)
					mod = {
						'path':p, 
						'markdown':url, 
						'code':'\n'.join(code), 
						'index':index+index_offset, 
						'tag':tag,
						'links':code_links,
						'include-dirs':code_idirs,
						'defines':code_defines,
					}
					if tag and '.' in tag:
						ext = tag.split('.')[-1].lower()
						#if ext in 'xml html js css py c cs h cpp hpp rust go java json'.split():
						mod['name'] = tag

					modules[ lang ].append( mod )
				in_code = False
				code = []
				code_links = []
				code_idirs = []
				index += 1
			# Start of a code block.
			else:
				in_code = True
				if prevline and prevline.strip().startswith('@'):
					tag = prevline.strip()[1:]
				else:
					tag = None

				lang = line.strip().split('```')[-1]
		# The middle of a code block.
		elif in_code:
			code.append(line)
		else:
			## import submarkdown file ##
			if line.startswith('* ') and '@import' in line and line.count('[')==1 and line.count(']')==1 and line.count('(')==1 and line.count(')')==1:
				submarkdown = line.split('(')[-1].split(')')[0].strip()
				subpath = os.path.join(base_path, submarkdown)
				if not os.path.isfile(subpath):
					raise RuntimeError('error: can not find markdown file: '+subpath)
				index += import_md( subpath, modules, index_offset=index )

			doc.append(line)

		prevline = line

	modules['markdown'] += '\n'.join(doc)
	if fences % 2:
		raise SyntaxError('invalid markdown - unclosed tripple back quote fence in: %s' %url)


	return index

def hack_nim_stdlib(code):
	'''
	already talked to the nim guys in irc, they dont know why these dl functions need to be stripped
	'''
	out = []
	for line in code.splitlines():
		if 'dlclose(' in line or 'dlopen(' in line or 'dlsym(' in line:
			pass
		else:
			out.append( line )
	return '\n'.join(out)


def build( modules, module_path, datadirs=None ):
	output = {'executeables':[], 'rust':[], 'c':[], 'c++':[], 'c#':[], 'go':[], 'javascript':[], 'java':[], 'xml':[], 'json':[], 'python':[], 'html':[], 'verilog':[], 'nim':[], 'lua':[], 'dart':[], 'datadirs':datadirs, 'datafiles':{}}
	python_main = {'name':'main.py', 'script':[]}
	go_main = {'name':'main.go', 'source':[]}
	tagged  = {}
	link    = []
	giws    = []   ## xml jni generator so c++ can call into java, blocks tagged with @gwis are compiled and linked with the final exe.
	java2rusthon = []
	nim_wrappers = []
	libdl = False ## provides: dlopen, dlclose, for dynamic libs. Nim needs this
	cached_json = {}

	if modules['json']:
		for mod in modules['json']:
			cached_json[ mod['name'] ] = mod['code']
			output['json'].append(mod)

	if modules['c#']:
		for mod in modules['c#']:
			output['c#'].append(mod)

	if modules['rapydscript']:
		for mod in modules['rapydscript']:
			tmprapyd = tempfile.gettempdir() + '/temp.rapyd'
			tmpjs = tempfile.gettempdir() + '/rapyd-output.js'
			open(tmprapyd, 'wb').write(mod['code'])
			subprocess.check_call(['rapydscript', tmprapyd, '--output', tmpjs])
			output['datafiles'][mod['tag']] = open(tmpjs,'rb').read()

	if modules['nim']:
		libdl = True
		## if compile_nim_lib is False then use old hack to compile nim source by extracting it and forcing into a single file.
		compile_nim_lib = True
		nimbin = os.path.expanduser('~/Nim/bin/nim')
		niminclude = os.path.expanduser('~/Nim/lib')

		if os.path.isfile(nimbin):
			mods_sorted_by_index = sorted(modules['nim'], key=lambda mod: mod.get('index'))
			for mod in mods_sorted_by_index:

				if mod['tag']:  ## save standalone nim program, can be run with `rusthon.py my.md --run=myapp.nim`
					output['nim'].append(mod)

				else:  ## use nim to translate to C and build later as staticlib
					tmpfile = tempfile.gettempdir() + '/rusthon_build.nim'
					nimsrc = mod['code'].replace('\t', '  ')  ## nim will not accept tabs, replace with two spaces.
					gen_nim_wrappers( nimsrc, nim_wrappers )
					open(tmpfile, 'wb').write( nimsrc )
					if compile_nim_lib:
						## lets nim compile the library
						#cmd = [nimbin, 'compile', '--app:staticLib', '--noMain', '--header']  ## staticlib has problems linking with dlopen,etc.
						cmd = [nimbin, 'compile', '--app:lib', '--noMain', '--header']
					else:
						cmd = [
							nimbin,
							'compile',
							'--header',
							'--noMain',
							'--noLinking',
							'--compileOnly',
							'--genScript',   ## broken?
							'--app:staticLib', ## Araq says staticlib and noMain will not work together.
							'--deadCodeElim:on',
						]
					if 'import threadpool' in nimsrc:
						cmd.append('--threads:on')
					cmd.append('rusthon_build.nim')

					print('-------- compile nim program -----------')
					print(' '.join(cmd))
					subprocess.check_call(cmd, cwd=tempfile.gettempdir())

					if compile_nim_lib:
						## staticlib broken in nim? missing dlopen
						libname = 'rusthon_build'
						link.append(libname)
						#output['c'].append({'source':mod['code'], 'staticlib':libname+'.a'})
						output['c'].append(
							{'source':mod['code'], 'dynamiclib':libname+'.so', 'name':'lib%s.so'%libname}

						)
					else:
						## get source from nim cache ##
						nimcache = os.path.join(tempfile.gettempdir(), 'nimcache')
						nim_stdlib = hack_nim_stdlib(
							open(os.path.join(nimcache,'stdlib_system.c'), 'rb').read()
						)
						#nim_header = open(os.path.join(nimcache,'rusthon_build.h'), 'rb').read()
						nim_code   = hack_nim_code(
							open(os.path.join(nimcache,'rusthon_build.c'), 'rb').read()
						)

						## gets compiled below
						cfg = {
							'dynamic'   : True,
							'link-dirs' :[nimcache, niminclude],
							#'build-dirs':[nimcache],  ## not working
							'index'    : mod['index'],
							'code'     : '\n'.join([nim_stdlib, nim_code])
							#'code'     : header
						}
						modules['c'].append( cfg )
		else:
			print('WARNING: can not find nim compiler')

	if modules['java']:
		mods_sorted_by_index = sorted(modules['java'], key=lambda mod: mod.get('index'))
		javafiles = []
		tmpdir = tempfile.gettempdir()
		for mod in mods_sorted_by_index:
			if mod['tag']=='java2rusthon':
				rcode = java_to_rusthon( mod['code'] )
				java2rusthon.append( rcode )
			elif 'name' in mod:
				jpath = os.path.join(tmpdir, mod['name'])
				if '/' in mod['name']:
					jdir,jname = os.path.split(jpath)
					if not os.path.isdir(jdir):
						os.makedirs(jdir)
				open(jpath, 'wb').write(mod['code'])
				javafiles.append( jpath )
			else:
				raise SyntaxError('java code must have a tag header: `java2rusthon` or a file path')

		if javafiles:
			output['java'].append( compile_java( javafiles ) )


	if modules['xml']:
		mods_sorted_by_index = sorted(modules['xml'], key=lambda mod: mod.get('index'))
		for mod in mods_sorted_by_index:
			if mod['tag']=='gwis':
				giws.append(mod['code'])  ## hand written bindings should get saved in output tar.
				bindings = compile_giws_bindings(mod['code'])
				modules['c++'].append( {'code':bindings, 'index': mod['index']})  ## gets compiled below
			else:
				output['xml'].append(mod)

	js_merge  = []
	cpp_merge = []
	cpp_links = []
	cpp_idirs = []
	cpp_defines = []
	compile_mode = 'binary'
	exename = 'rusthon-test-bin'


	if modules['rusthon']:
		mods_sorted_by_index = sorted(modules['rusthon'], key=lambda mod: mod.get('index'))
		for mod in mods_sorted_by_index:
			script = mod['code']
			index = mod.get('index')
			header = script.splitlines()[0]
			backend = 'c++'  ## default to c++ backend
			if header.startswith('#backend:'):
				backend = header.split(':')[-1].strip()
				if ' ' in backend:
					backend, compile_mode = backend.split(' ')
				if '\t' in backend:
					backend, compile_mode = backend.split('\t')

				if backend not in 'c++ rust javascript go verilog dart lua'.split():
					raise SyntaxError('invalid backend: %s' %backend)

				if compile_mode and compile_mode not in 'binary staticlib dynamiclib'.split():
					raise SyntaxError('invalid backend option <%s> (valid types: binary, staticlib, dynamiclib)' %backend)

			if backend == 'verilog':
				vcode = translate_to_verilog( script )
				modules['verilog'].append( {'code':vcode, 'index': index})  ## gets compiled below

			elif backend == 'c++':
				if mod['tag'] and mod['tag'] and '.' not in mod['tag']:
					exename = mod['tag']

				## user named output for external build tools that need .h,.hpp,.cpp, files output to hardcoded paths.
				if mod['tag'] and (mod['tag'].endswith('.h') or mod['tag'].endswith('.hpp') or mod['tag'].endswith('.cpp')):
					pyjs = python_to_pythonjs(script, cpp=True, module_path=module_path)
					pak = translate_to_cpp(
						pyjs, 
						cached_json_files=cached_json, 
						insert_runtime=False
					)
					## pak contains: c_header and cpp_header
					output['datafiles'][ mod['tag'] ] = pak['main']  ## save to output c++ to tar

					if 'user-headers' in pak:
						for classtag in pak['user-headers'].keys():
							classheader = pak['user-headers'][ classtag ]
							headerfile  = classheader['file']
							if headerfile in output['datafiles']:
								output['datafiles'][ headerfile ] += '\n' + '\n'.join(classheader['source'])
							else:
								output['datafiles'][ headerfile ] = '\n'  + '\n'.join(classheader['source'])

				else:
					cpp_merge.append(script)

					if 'links' in mod:
						cpp_links.extend(mod['links'])
					if 'include-dirs' in mod:
						cpp_idirs.extend(mod['include-dirs'])
					if 'defines' in mod:
						cpp_defines.extend(mod['defines'])

			elif backend == 'rust':
				pyjs = python_to_pythonjs(script, rust=True, module_path=module_path)
				rustcode = translate_to_rust( pyjs )
				modules['rust'].append( {'code':rustcode, 'index': index})  ## gets compiled below

			elif backend == 'go':
				pyjs = python_to_pythonjs(script, go=True, module_path=module_path)
				gocode = translate_to_go( pyjs )
				#modules['go'].append( {'code':gocode})  ## gets compiled below
				go_main['source'].append( gocode )

			elif backend == 'javascript':
				if mod['tag']:  ## saves to external js file
					js = compile_js( mod['code'], module_path, main_name=mod['tag'] )
					mod['build'] = {'script':js[mod['tag']]}
					tagged[ mod['tag'] ] = js[mod['tag']]
					for name in js:
						output['javascript'].append( {'name':name, 'script':js[name], 'index': index} )
				else:
					js_merge.append(mod)

			elif backend == 'lua':
				pyjs = python_to_pythonjs(script, lua=True, module_path=module_path)
				luacode = translate_to_lua( pyjs )
				name = 'main.lua'
				if mod['tag']: name = mod['tag']
				if not name.endswith('.lua'): name += '.lua'
				output['lua'].append( {'name':name, 'script':luacode, 'index': index} )

			elif backend == 'dart':
				pyjs = python_to_pythonjs(script, dart=True, module_path=module_path)
				dartcode = translate_to_dart( pyjs )
				name = 'main.dart'
				if mod['tag']: name = mod['tag']
				if not name.endswith('.dart'): name += '.dart'
				output['dart'].append( {'name':name, 'script':dartcode, 'index': index} )

	if js_merge:
		tagname = None
		src = []
		for mod in js_merge:
			if mod['tag']:
				if tagname is not None:
					raise RuntimeError('TODO multiple tag insertions')
				tagname = mod['tag']
				src.append( mod['code'] )
			else:
				src.append(mod['code'])

			assert tagname
			js = compile_js( '\n'.join(src), module_path, main_name=tagname )
			tagged[ tagname ] = js[ tagname ]
			for name in js:
				output['javascript'].append( {'name':name, 'script':js[name], 'index': index} )

	cpyembed = []
	nuitka = []
	nuitka_include_path = None  ## TODO option for this
	nuitka_module_name  = 'unnamed_nuitka_module'
	if modules['python']:
		mods_sorted_by_index = sorted(modules['python'], key=lambda mod: mod.get('index'))
		for mod in mods_sorted_by_index:
			if mod['tag']:
				name = mod['tag']
				if name == 'nuitka' or name.startswith('nuitka:'):
					if ':' in name:
						nuitka_module_name = name.split(':')[-1]
					if not len(nuitka):
						## __file__ is undefined when CPython is embedded
						#cpyembed.append('sys.path.append(os.path.dirname(__file__))')
						#cpyembed.append('print sys.argv')  ## also undefined
						cpyembed.append('import sys')
						cpyembed.append('sys.path.append("./")')
						cpyembed.append('from %s import *'%nuitka_module_name)

					nuitka.append(mod['code'])

				elif name == 'embed' or name == 'embed:cpython':
					cpyembed.append(mod['code'])
				else:
					if not name.endswith('.py'):
						name += '.py'
					output['python'].append( {'name':name, 'script':mod['code']} )
			else:
				if len(output['python'])==0:
					python_main['script'].append( mod['code'] )
				else:
					output['python'][-1]['script'] += '\n' + mod['code']


	if cpp_merge:
		merge = []
		nuitka_funcs = []
		if java2rusthon:
			merge.extend(java2rusthon)
			java2rusthon = None
		if nim_wrappers:
			## inserts generated rusthon nim wrappers into script before translation ##
			nim_wrappers.insert(0,'# nim wrappers generated by rusthon #')
			nim_wrappers.insert(1, 'with extern(abi="C"):')
			merge.extend(nim_wrappers)
		if nuitka:
			#npak = nuitka_compile_integrated('\n'.join(nuitka), nuitka_funcs)
			#for h in npak['files']:
			#	modules['c++'].append(
			#		{'code':h['data'], 'tag':h['name'], 'index':0}
			#	)
			nsrc = '\n'.join(nuitka)
			output['c++'].append(
				{
					'staticlib'   : nuitka_compile( nsrc, nuitka_module_name ),
					'source-name' : 'my_nuitka_module.py',
					'name'        : 'my_nuitka_module.so',
					'source'      : nsrc,
				}
			)

		merge.extend(cpp_merge)
		script = '\n'.join(merge)
		pyjs = python_to_pythonjs(script, cpp=True, module_path=module_path)
		pak = translate_to_cpp( pyjs, cached_json_files=cached_json )   ## pak contains: c_header and cpp_header
		n = len(modules['c++']) + len(giws)
		cppcode = pak['main']
		#if nuitka:
		#	cppcode = npak['main'] + '\n' + cppcode
		if cpyembed:
			inlinepy = ('\n'.join(cpyembed)).replace('\n', '\\n').replace('"', '\\"')
			staticstr = 'const char* __python_main_script__ = "%s";\n' %inlinepy
			cppcode = staticstr + cppcode
		modules['c++'].append(
			{'code':cppcode, 'index':n+1, 'links':cpp_links, 'include-dirs':cpp_idirs, 'defines':cpp_defines}
		)  ## gets compiled below



	if modules['html']:
		mods_sorted_by_index = sorted(modules['html'], key=lambda mod: mod.get('index'))
		for mod in mods_sorted_by_index:
			html = []
			for line in mod['code'].splitlines():
				## `~/some/path/myscript.js` special syntax to copy javascript directly into the output html, good for testing locally.
				if line.strip().startswith('<script ') and line.strip().endswith('</script>') and 'src="~/' in line:
					url = line.split('src="')[-1].split('"')[0]
					url = os.path.expanduser( url )
					if os.path.isfile(url):
						html.append('<script type="text/javascript">')
						html.append( open(url, 'rb').read() )
						html.append('</script>')
					else:
						print('WARNING: could not find file: %s' %url)
						html.append( line )
				else:
					html.append( line )

			html = '\n'.join(html)

			for tagname in tagged:
				tag = '<@%s>' %tagname
				js  = tagged[tagname]
				if tag in html:
					html = html.replace(tag, '<script type="text/javascript">\n%s</script>' %js)
			mod['code'] = html
			output['html'].append( mod )

	if modules['verilog']:
		source = []
		mainmod = None
		mods_sorted_by_index = sorted(modules['verilog'], key=lambda mod: mod.get('index'))
		for mod in mods_sorted_by_index:
			source.append( mod['code'] )
			if 'name' in mod and mod['name']=='main':
				mainmod = mod
			elif mainmod is None:
				mainmod = mod

		source = '\n'.join(source)

		mod = {}
		output['verilog'].append(mod)

		if os.path.isfile('/usr/bin/iverilog') or os.path.isfile('/usr/local/bin/iverilog'):
			mod['source'] = source
			mod['binary'] = tempfile.gettempdir() + '/rusthon-sv-build.vvp'
			mod['name']   = 'main.vvp'
			output['executeables'].append( mod['binary'] )
			tmpfile = tempfile.gettempdir() + '/rusthon-verilog-build.sv'
			open(tmpfile, 'wb').write( source )
			## note: iverilog defaults to verilog mode, not systemverilog, `-g2005-sv` is required. '-g2012' also works.
			cmd = [
				'iverilog',
				'-g2005-sv',
				'-o',
				'rusthon-sv-build.vvp',
				tmpfile
			]
			p = subprocess.Popen(cmd, cwd=tempfile.gettempdir(), stdout=subprocess.PIPE, stderr=subprocess.PIPE )
			p.wait()
			if p.returncode != 0:
				srclines = source.splitlines()
				err = p.stderr.read()  ## ends with "I give up."
				errors = []
				for line in err.splitlines():
					if 'syntax error' in line:
						errors.append('- - - - - - - - - - - -')
						lineno = int( line.split(':')[-2] )
						e = [
							'Syntax Error - line: %s' %lineno,
						]
						if lineno-2 < len(srclines):
							e.append( srclines[lineno-2] )
						if lineno-1 < len(srclines):
							e.append( srclines[lineno-1] )
						if lineno < len(srclines):
							e.append( srclines[lineno] )

						errors.extend( e )
					else:
						errors.append(line)

				msg = [' '.join(cmd)]
				for i,line in enumerate(source.splitlines()):
					msg.append('%s:	%s' %(i+1, line))
				msg.extend(errors)
				raise RuntimeError('\n'.join(msg))


		else:
			print('WARNING: could not find iverilog')
			mod['code'] = source

	if modules['go']:
		for mod in modules['go']:
			if 'name' in mod:
				name = mod['name']
				if name=='main':
					go_main['source'].append( mod['code'] )
				else:
					output['go'].append( mod )
			else:
				go_main['source'].append( mod['code'] )

	if go_main['source']:
		go_main['source'] = '\n'.join(go_main['source'])
		output['go'].insert( 0, go_main )

	if output['go']:
		source = [ mod['source'] for mod in output['go'] ]
		tmpfile = tempfile.gettempdir() + '/rusthon-go-build.go'
		open(tmpfile, 'wb').write( '\n'.join(source) )
		cmd = ['go', 'build', tmpfile]
		subprocess.check_call(['go', 'build', tmpfile], cwd=tempfile.gettempdir() )
		mod['binary'] = tempfile.gettempdir() + '/rusthon-go-build'
		output['executeables'].append(tempfile.gettempdir() + '/rusthon-go-build')


	if modules['rust']:
		source = []
		mainmod = None
		mods_sorted_by_index = sorted(modules['rust'], key=lambda mod: mod.get('index'))
		for mod in mods_sorted_by_index:
			source.append( mod['code'] )
			if 'name' in mod and mod['name']=='main':
				mainmod = mod
			elif mainmod is None:
				mainmod = mod

		tmpfile = tempfile.gettempdir() + '/rusthon-build.rs'
		data = '\n'.join(source)
		open(tmpfile, 'wb').write( data )

		pak = None
		if modules['c++']:
			libname = 'rusthon-lib%s' %len(output['rust'])
			link.append(libname)
			subprocess.check_call(['rustc', '--crate-name', 'rusthon', '--crate-type', 'staticlib' ,'-o', tempfile.gettempdir() + '/'+libname,  tmpfile] )
			pak = {'source':data, 'staticlib':libname, 'name':'lib'+libname+'.a'}

		else:
			subprocess.check_call(['rustc', '--crate-name', 'rusthon', '-o', tempfile.gettempdir() + '/rusthon-bin',  tmpfile] )
			pak = {'source':data, 'binary':tempfile.gettempdir() + '/rusthon-bin', 'name':'rusthon-bin'}
			output['executeables'].append(tempfile.gettempdir() + '/rusthon-bin')

		assert pak
		mainmod['build'] = pak
		output['rust'].append( pak )


	if modules['c']:
		dynamiclib = False
		source   = []
		cinclude = []
		cbuild   = []
		mods_sorted_by_index = sorted(modules['c'], key=lambda mod: mod.get('index'))
		for mod in mods_sorted_by_index:
			if 'dynamic' in mod and mod['dynamic']:
				dynamiclib = True
			if 'link-dirs' in mod:
				cinclude.extend(mod['link-dirs'])
			if 'build-dirs' in mod:
				for bdir in mod['build-dirs']:
					for fname in os.listdir(bdir):
						if fname.endswith('.c'):
							cbuild.append(os.path.join(bdir,fname))

			if 'code' in mod and mod['code']:
				source.append( mod['code'] )
			else:
				## module must contain a build config
				raise RuntimeError('missing code')

		if source:
			data = '\n'.join(source)
			cpak = {'source':data}
			output['c'].append(cpak)

			libname = 'default-clib%s' %len(output['c'])  ## TODO user named
			link.append(libname)
			dynamic_path = tempfile.gettempdir() + '/lib'+libname+'.so'
			static_path = tempfile.gettempdir() + '/lib'+libname+'.a'
			object_path = tempfile.gettempdir() + '/'+libname+'.o'


			tmpfile = tempfile.gettempdir() + '/rusthon-build.c'
			open(tmpfile, 'wb').write( data )

			cmd = ['gcc']
			for idir in cinclude:
				cmd.append('-I'+idir)
			cmd.extend(['-c', tmpfile])


			if dynamiclib:
				cmd.extend(
					[
						'-fPIC',
						'-O3',
						'-fomit-frame-pointer',
						'-Wall', '-Wno-unused',
						'-o', object_path
					]
				)
				subprocess.check_call(cmd)

				cmd = [
					'gcc',
					'-shared',
					'-Wl,-soname,lib%s.so' %libname,
					#'-Wl,-rpath,/tmp',
					'-Wl,--export-dynamic',
					'-pthread', '-o', dynamic_path,
					object_path
				]
				subprocess.check_call(cmd)
				cpak['dynamiclib'] = dynamic_path
				cpak['name']       = 'lib%s.so' %libname

			else:

				if cbuild:
					#gcc: fatal error: cannot specify -o with -c, -S or -E with multiple files
					#cmd.extend(cbuild)  ## extra c files `/some/path/*.c`
					raise RuntimeError('TODO fix building multiple .c files at once using gcc option -o')

				cmd.extend(['-o', object_path ])

				print('========== compiling C static library =========')
				print(' '.join(cmd))
				subprocess.check_call( cmd )
				print('========== ar : staticlib ==========')
				cmd = ['ar', 'rcs', static_path, object_path]
				subprocess.check_call( cmd )
				cpak['staticlib'] = libname+'.a'
				cpak['name']      = libname+'.a'


	if modules['c++']:
		links = []
		idirs = []
		source = []
		defines = []
		mods_sorted_by_index = sorted(modules['c++'], key=lambda mod: mod.get('index'))
		mainmod = None
		builddir = tempfile.gettempdir()
		#compile_mode = 'binary'
		for mod in mods_sorted_by_index:
			if 'tag' in mod and mod['tag'] and mod['tag'].endswith('.hpp'):
				## allows plain header files to be included in build directory ##
				open(
					os.path.join(builddir, mod['tag']), 'wb'
				).write( mod['code'] )
				output['c++'].append( mod )
			else:
				source.append( mod['code'] )

			if 'name' in mod and mod['name']=='main':
				mainmod = mod
			elif mainmod is None:
				mainmod = mod
			if 'links' in mod:
				links.extend(mod['links'])
			if 'include-dirs' in mod:
				idirs.extend(mod['include-dirs'])
			if 'defines' in mod:
				defines.extend(mod['defines'])

			#if 'compile-mode' in mod:
			#	compile_mode = mod['compile-mode']

			if 'tag' in mod and '.' not in mod['tag']:
				exename = mod['tag']

		tmpfile = builddir + '/rusthon-c++-build.cpp'
		data = '\n'.join(source)
		open(tmpfile, 'wb').write( data )
		cmd = ['g++']

		if compile_mode=='binary':
			cmd.extend(['-O3', '-fprofile-generate', '-march=native', '-mtune=native', '-I'+tempfile.gettempdir()])

		cmd.append('-Wl,-rpath,./')  ## can not load dynamic libs from same directory without this
		cmd.append(tmpfile)

		if '/' in exename and not os.path.isdir( os.path.join(builddir,os.path.split(exename)[0]) ):
			os.makedirs(os.path.join(builddir,os.path.split(exename)[0]))

		if compile_mode == 'binary':
			cmd.extend(['-o', os.path.join(builddir,exename)])
		elif compile_mode == 'dynamiclib':
			cmd.extend(
				['-shared', '-fPIC']
			)
			exename += '.so'
			cmd.extend(['-o', os.path.join(builddir,exename)])

		cmd.extend(
			['-pthread', '-std=c++11' ]
		)

		for D in defines:
			cmd.append('-D%s' %D)

		if nuitka:
			## note: linking happens after the object-bin above is created `-o ruston-c++-bin`,
			## fixes the error: undefined reference to `_PyThreadState_Current', etc.
			#if not nuitka_include_path:
			#	nuitka_include_path = '/usr/local/lib/python2.7/dist-packages/nuitka/build/include'
			#cmd.append('-I'+nuitka_include_path)
			cmd.append('-I/usr/include/python2.7')
			cmd.append('-lpython2.7')

		if idirs:
			for idir in idirs:
				cmd.append('-I'+idir)

		if links:
			for lib in links:
				cmd.append('-l'+lib)

		if link or giws:

			if libdl:
				cmd.append('-ldl')

			if giws:   ## link to the JVM if giws bindings were compiled ##
				cmd.append('-ljvm')

				os.environ['LD_LIBRARY_PATH']=''
				#for jrepath in 'include include/linux jre/lib/i386 jre/lib/i386/client/'.split():
				for jrepath in 'include include/linux'.split():
					cmd.append('-I%s/%s' %(os.environ['JAVA_HOME'], jrepath))
				for jrepath in 'jre/lib/amd64 jre/lib/amd64/server/'.split():
					cmd.append('-L%s/%s' %(os.environ['JAVA_HOME'], jrepath))
					os.environ['LD_LIBRARY_PATH'] += ':%s/%s'%(os.environ['JAVA_HOME'], jrepath)
				#raise RuntimeError(os.environ['LD_LIBRARY_PATH'])

			#else:  ## TODO fix jvm with static c libs
			#	cmd.append('-static')

			if link:  ## c staticlibs or giws c++ wrappers ##
				cmd.append('-L' + tempfile.gettempdir() + '/.')
				for libname in link:
					cmd.append('-l'+libname)

		print('========== g++ : compile main ==========')
		print(' '.join(cmd))
		subprocess.check_call( cmd )
		mainmod['build'] = {
			'source':data, 
			'binary':tempfile.gettempdir() + '/' + exename, 
			'name':exename
		}
		if compile_mode == 'binary':
			output['c++'].append( mainmod['build'] )
			output['executeables'].append(tempfile.gettempdir() + '/' + exename)
		else:
			output['datafiles'][ exename ] = open(tempfile.gettempdir() + '/' + exename, 'rb').read()

	if python_main['script']:
		python_main['script'] = '\n'.join(python_main['script'])
		output['python'].append( python_main )

	return output

def get_first_build_from_package(package):
	for lang in 'rust c++ go javascript python html verilog java nim dart lua'.split():
		for pak in package[lang]:
			return pak

def save_tar( package, path='build.tar' ):
	import tarfile
	import StringIO
	tar = tarfile.TarFile(path,"w")

	if package['datadirs']:
		for datadir in package['datadirs']:
			if os.path.isdir(datadir):
				for name in os.listdir(datadir):
					a = os.path.join(datadir,name)
					tar.add(a)  ## files and folders
			elif os.path.isfile(datadir):
				tar.add(datadir)

	if package['datafiles']:
		for fpath in package['datafiles']:
			fdata = package['datafiles'][fpath]
			s = StringIO.StringIO()
			s.write( fdata )
			s.seek(0)
			ti = tarfile.TarInfo(name=fpath)
			ti.size=len(s.buf)
			tar.addfile(tarinfo=ti, fileobj=s)

	exts = {'rust':'.rs', 'c++':'.cpp', 'c#':'.cs', 'javascript':'.js', 'json':'.json', 'python':'.py', 'go':'.go', 'html': '.html', 'verilog':'.sv', 'nim':'.nim', 'java':'.java', 'dart':'.dart', 'lua':'.lua'}
	for lang in 'rust c c++ c# go javascript json python xml html verilog java nim dart lua'.split():
		for info in package[lang]:
			name = 'untitled'
			if 'name' in info: name = info['name']

			source = False
			is_bin = False
			s = StringIO.StringIO()
			if 'dynamiclib' in info:
				s.write(open(info['dynamiclib'],'rb').read())
				if 'source' in info:
					source = info['source']
			elif 'staticlib' in info:
				s.write(open(info['staticlib'],'rb').read())
				if 'source' in info:
					source = info['source']
			elif 'binary' in info:
				s.write(open(info['binary'],'rb').read())
				source = info['source']
				is_bin = True
			elif 'code' in info:
				if lang=='verilog': print(info['code'])  ## just for testing.
				s.write(info['code'])
			elif 'script' in info:
				s.write(info['script'])
			s.seek(0)

			if not is_bin and not source and not name.endswith( exts[lang] ) and '.' not in name:
				name += exts[lang]

			ti = tarfile.TarInfo(name=name)
			ti.size=len(s.buf)
			if is_bin: ti.mode = 0o777
			tar.addfile(tarinfo=ti, fileobj=s)

			if source:
				s = StringIO.StringIO()
				s.write(source)
				s.seek(0)
				if 'source-name' in info:
					ti = tarfile.TarInfo( name = info['source-name'] )
				else:
					ti = tarfile.TarInfo( name = name + '-source' + exts[lang] )
				ti.size=len(s.buf)
				tar.addfile(tarinfo=ti, fileobj=s)

	tar.close()


def main():
	if len(sys.argv)==1:
		print('usage: ./rusthon.py [python files] [markdown files] [tar file] [--anaconda] [--run=] [--data=]')
		print('		[tar file] is the optional name of the output tar that contains the build')
		print()
		print('		source files, transpiled source, and output binaries.')
		print()
		print('		--run is given a list of programs to run, "--run=a.py,b.py"')
		print('		a.py and b.py can be run this way by naming the code blocks in the markdown')
		print('		using the tag syntax "@a.py" on the line before the code block.')
		print()
		print('		--data is given a list of directories to include in the build dir and tarfile.')
		print()
		print('		--anaconda run scripts with Anaconda Python, must be installed to ~/anaconda')
		return

	modules = new_module()

	save = False
	paths = []
	scripts = []
	markdowns = []
	gen_md = False
	output_tar  = 'rusthon-build.tar'
	output_dir  = None
	output_file = None
	launch = []
	datadirs = []
	j2r = False
	anaconda = False

	for arg in sys.argv[1:]:
		if os.path.isdir(arg):
			paths.append(arg)
		elif arg.startswith('--data='):
			datadirs.extend( arg.split('=')[-1].split(',') )
		elif arg.startswith('--run='):
			launch.extend( arg.split('=')[-1].split(',') )
			save = True
		elif arg.startswith('--output='):
			output_file = arg.split('=')[-1]
		elif arg.startswith('--output-dir='):
			output_dir = arg.split('=')[-1]
			if output_dir.startswith('~'):
				output_dir = os.path.expanduser(output_dir)

		elif arg.endswith('.py'):
			scripts.append(arg)
		elif arg.endswith('.md'):
			markdowns.append(arg)
		elif arg.endswith('.tar'):
			output_tar = arg
			save = True
		elif arg =='--generate-markdown':
			gen_md = True
		elif arg == '--tar':
			save = True
		elif arg == '--java2rusthon':
			j2r = True
		elif arg == '--anaconda':
			anaconda = True

	datadirs = [os.path.expanduser(dd) for dd in datadirs]

	if j2r:
		for path in paths:
			m = convert_to_markdown_project(path, java=True, java2rusthon=True)
			raise RuntimeError('TODO: %s'%m)

	if gen_md:
		for path in paths:
			mds = convert_to_markdown_project(path)
			if not output_file:
				raise RuntimeError('%s \n ERROR: no output file given `--output=myproject.md`'%mds)
			elif os.path.isdir(output_file):
				## write as multiple markdowns into directory
				for m in mds:
					if m['name'].count('.')==1:
						mname = m['name'].split('.')[0] + '.md'
					else:
						mname = m['name'] + '.md'
					mpath = os.path.join(output_file, mname)
					print('writing-> %s'%mpath)
					open(mpath, 'wb').write(m['markdown'])
			else:
				if not output_file.endswith('.md'):
					output_file += '.md'
				md = '\n'.join([m['markdown'] for m in mds])
				open(output_file, 'wb').write(md)
			sys.exit()


	base_path = None
	singleout = None
	for path in scripts:
		script = open(path,'rb').read()
		if '--c++' in sys.argv:          script = '#backend:c++\n'+script
		elif '--javascript' in sys.argv: script = '#backend:javascript\n'+script
		elif '--rust' in sys.argv: script = '#backend:rust\n'+script
		elif '--go' in sys.argv:   script = '#backend:go\n'+script
		elif '--dart' in sys.argv: script = '#backend:dart\n'+script
		elif '--lua' in sys.argv:  script = '#backend:lua\n'+script
		elif '--verilog' in sys.argv: script = '#backend:verilog\n'+script
		fpath,fname = os.path.split(path)
		tag = fname.split('.')[0]
		singlemod = {'name':'main', 'tag':tag, 'code':script}
		modules['rusthon'].append( singlemod )
		if base_path is None:
			base_path = os.path.split(path)[0]
		if singleout is None and output_file:
			singleout = singlemod

	for path in markdowns:
		import_md( path, modules=modules )
		if base_path is None:
			base_path = os.path.split(path)[0]

	package = build(modules, base_path, datadirs=datadirs )
	if singleout:
		pak = get_first_build_from_package(package)
		if 'source' in pak:
			open(output_file, 'wb').write(pak['source'])
		elif 'code' in pak:
			open(output_file, 'wb').write(pak['code'])
		elif 'script' in pak:
			open(output_file, 'wb').write(pak['script'])
		else:
			raise RuntimeError(pak)
		print('saved output to: %s'%output_file)

	elif not save:
		tmpdir = tempfile.gettempdir()
		## copy jar and other extra libraries files files ##
		for p in datadirs:
			## saves jar and other files like dynamic libraries,
			## needed to do quick testing.
			if '.' in p:
				dpath,dname = os.path.split(p)
				open(os.path.join(tmpdir,dname),'wb').write(open(p,'rb').read())

		for exe in package['executeables']:
			print('running: %s' %exe)
			subprocess.check_call(
				exe,
				cwd=tmpdir ## jvm needs this to find the .class files
			)

		if package['html']:
			import webbrowser
			for i,page in enumerate(package['html']):
				tmp = tempfile.gettempdir() + '/rusthon-webpage%s.html' %i
				open(tmp, 'wb').write( page['code'] )
				webbrowser.open(tmp)

	else:
		save_tar( package, output_tar )
		print('saved build to:')
		print(output_tar)

		if launch:
			tmpdir = output_dir or tempfile.gettempdir()
			tmptar = os.path.join(tmpdir, 'temp.tar')
			open(tmptar, 'wb').write(
				open(output_tar, 'rb').read()
			)
			subprocess.check_call( ['tar', '-xvf', tmptar], cwd=tmpdir )

			for name in launch:
				if name.endswith('.py'):
					firstline = open(os.path.join(tmpdir, name), 'rb').readlines()[0]
					python = 'python'
					if firstline.startswith('#!'):
						if 'python3' in firstline:
							python = 'python3'

					if anaconda:
						## assume that the user installed anaconda to the default location ##
						anabin = os.path.expanduser('~/anaconda/bin')
						if not os.path.isdir(anabin):
							raise RuntimeError('Anaconda Python not installed to default location: %s' %anabin)

						subprocess.call( [os.path.join(anabin,python), name], cwd=tmpdir )

					else:
						subprocess.call( [python, name], cwd=tmpdir )

				elif name.endswith('.js'):
					subprocess.call( ['node', name],   cwd=tmpdir )

				elif name.endswith('.nim'):
					subprocess.call( ['nim', 'compile', '--run', name],   cwd=tmpdir )

				elif name.endswith('.go'):
					subprocess.call( ['go', 'run', name],   cwd=tmpdir )

				elif name.endswith('.lua'):
					subprocess.call( ['luajit', name],   cwd=tmpdir )

				elif name.endswith('.dart'):
					dartbin = os.path.expanduser('~/dart-sdk/bin/dart')
					subprocess.call( [dartbin, name],   cwd=tmpdir )

				else:
					subprocess.call( [name], cwd=tmpdir )


def bootstrap_rusthon():
	localdir = os.path.dirname(unicode(__file__, sys.getfilesystemencoding()))
	mods = new_module()
	import_md( os.path.join(localdir,'src/main.md'), modules=mods )
	src = []
	mods_sorted_by_index = sorted(mods['python'], key=lambda mod: mod.get('index'))
	for mod in mods_sorted_by_index:  ## this is simplified because rusthon's source is pure python
		src.append( mod['code'] )
	src = '\n'.join(src)
	if '--dump' in sys.argv: open('/tmp/bootstrap-rusthon.py', 'wb').write(src)
	exec(src, globals())

	if '--test' in sys.argv:
		test_typedpython()  ## runs some basic tests on the extended syntax

	if '--runtime' in sys.argv:
		print('creating new runtime: pythonjs.js')
		open('pythonjs.js', 'wb').write( generate_js_runtime() )
	if '--miniruntime' in sys.argv:
		print('creating new runtime: pythonjs-minimal.js')
		open('pythonjs-minimal.js', 'wb').write( generate_minimal_js_runtime() )


if __name__ == '__main__':
	bootstrap_rusthon()
	main()

