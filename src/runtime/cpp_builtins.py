# Cppthon builtins
# by Brett Hartshorn - copyright 2014
# License: "New BSD"


## note the caller must catch and clean up using `free` on errors
## `catch (...)` will leak memory, and should only be a fallback
## from external c++ libs that throw const references of std::exception
def RuntimeError( msg:string ) -> std::runtime_error*:
	prefix = "RuntimeError|"
	return inline('new std::runtime_error(prefix+msg)')

def IOError( msg:string ) -> std::runtime_error*:
	prefix = "IOError|"
	return inline('new std::runtime_error(prefix+msg)')


#def __split_string_py__(s:string, m:string) ->[]string:
#	vec = []string("")
#	for c in s:
#		if c == m:
#			vec[-1].append("")
#		else:
#			vec[-1] += c
#	return vec


## note: try/catch can be optional to be compatible with external build tools that disable exceptions
def __open__( name:string, mode: string) -> std::fstream*:
	try:
		let s : std::fstream*

		if mode=="rb" or mode=="r":
			options = inline('std::fstream::in | std::fstream::binary')
			s = new std::fstream(name.c_str(), options)
		else:
			s = new std::fstream(name.c_str(), std::fstream::out | std::fstream::binary)
		with pointers:
			s.exceptions( std::ios::failbit | std::ios::badbit | std::ios::eofbit )
		return s
	except:
		inline('throw IOError(std::string("No such file or directory: ")+name)')



inline("""

const char* cstr( std::string s ) { return s.c_str(); }

std::string __string_upper__( std::string s ) {
	auto a = std::string("");
	for (auto c: s) {
		a += std::toupper(c);
	}
	return a;
}

std::string __string_lower__( std::string s ) {
	auto a = std::string("");
	for (auto c: s) {
		a += std::tolower(c);
	}
	return a;
}

std::shared_ptr<std::vector<std::string>> __split_string__(std::string s, std::string c) {
	auto vec = std::vector<std::string>();
	vec.push_back(std::string(""));
	for (auto i=0; i<s.size()-1; i++) {
		auto v = std::string(&s.at(i));
		v.resize(1);
		if (v == c) {
			vec.push_back(std::string(""));
		} else {
			vec.back() += v;
		}
	}
	return std::make_shared<std::vector<std::string>>(vec);
}

double __double__(int a) { return (double)a; }

int sum(std::shared_ptr<std::vector<int>> arr) {
	int s = 0;
	std::for_each(arr->begin(),arr->end(),[&](int n){s += n;});
	return s;
}
double sumd(std::shared_ptr<std::vector<double>> arr) {
	double s = 0.0;
	std::for_each(arr->begin(),arr->end(),[&](double n){s += n;});
	return s;
}
float sumf(std::shared_ptr<std::vector<float>> arr) {
	float s = 0.0;
	std::for_each(arr->begin(),arr->end(),[&](float n){s += n;});
	return s;
}


std::string str( const std::string s ) {
	return s;
}
std::string str( int s ) {
	return std::to_string(s);
}

std::string readfile(std::fstream* f) {
	std::ostringstream c;
	c << f->rdbuf();
	f->close();
	return c.str();
}

// a pointer version is also required for `range` because it could be called inside
// a `with pointers:` block, in this special case return a copy and let the caller
// take the pointer.
std::vector<int> __range1__( int n ) {
	std::vector<int> vec(n);
	for (int i=0; i<n; i++) {
		vec[i] = i;
	}
	return vec;
}


std::shared_ptr<std::vector<int>> range1( int n ) {
	std::vector<int> vec(n);
	for (int i=0; i<n; i++) {
		vec[i] = i;
	}
	return std::make_shared<std::vector<int>>(vec);
}

std::shared_ptr<std::vector<int>> range2( int start, int end ) {
	std::vector<int> vec(end-start);
	int index = 0;
	for (int i=start; i<end; i++) {
		vec[index] = i;
		index ++;
	}
	return std::make_shared<std::vector<int>>(vec);
}

int ord( std::string s) {
	int r = (int)s.c_str()[0];
	return r;
}

double __float__( std::string s ) {
	return std::stod( s );
}

double round( double n, int places ) {
	auto p = std::pow(10, places);
	return std::round(n * p) / p;
}

std::string chr( int c ) {
	//return std::to_string( static_cast<char>(c) );  // as a oneliner it fails?
	auto s = static_cast<char>(c);
	return std::string( &s );
}

std::string __parse_error_type__( std::runtime_error* err) {
	auto vec = __split_string__( std::string(err->what()), std::string("|") );
	return (*vec)[0];
}

/*end-builtins*/
""")




