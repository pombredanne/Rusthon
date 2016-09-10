'''
simple subclass
'''
class A:
	def __init__(self, x:int, y:int, z:int):
		self.x = x
		self.y = y
		self.z = z

	def mymethod(self, m:int) -> int:
		return self.x * m

class B(A):
	def __init__(self, s:string):
		A.__init__(self, 4, 5, 6)
		let self.w : string = s
		let self.x : int    = 1

	def method2(self, v:string) ->string:
		print(self.x)
		self.w = v
		## returning `self.w` or `v` is not allowed in Rust,
		## because `v` is now owned by `self`
		#return self.w
		return "ok"

def call_method( cb:lambda(int)(int), mx:int ) ->int:
	return cb(mx)

def main():
	a = A( 100, 200, 9999 )
	print( a.x )
	print( a.y )
	print( a.z )

	b = a.mymethod(3)
	print( b )

	c = call_method( lambda W=int: a.mymethod(W), 4 )
	print( c )

	x = B('testing...')
	print( x.method2('hello world') )
	print( x.w )
