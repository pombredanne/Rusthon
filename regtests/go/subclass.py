'''
simple class
'''
class A:
	def __init__(self, x:int, y:int, z:int=1):
		let self.x : int = x
		let self.y : int = y
		let self.z : int = z

	def mymethod(self, m:int) -> int:
		return self.x * m

class B(A):
	def __init__(self, s:string):
		let self.w : string = s
		let self.x : int = 1

	def method2(self, v:string) ->string:
		print(self.x)
		self.w = v
		return self.w

def call_method( cb:func(int)(int), mx:int ) ->int:
	return cb(mx)

def main():
	a = A( 100, 200, z=9999 )
	print( a.x )
	print( a.y )
	print( a.z )

	b = a.mymethod(3)
	print( b )

	c = call_method( a.mymethod, 4 )
	print( c )

	x = B('testing...')
	print( x.method2('hello world') )