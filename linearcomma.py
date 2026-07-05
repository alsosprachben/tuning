#!/usr/bin/env python

import decimal

decimal.getcontext().prec = 20
goal_digits = 9
goal = decimal.Decimal(1) / 10 ** goal_digits

class Comma:
	def __init__(self):
		self.c = 12
		self.rn = 3
		self.rd = 2
		self.v = None
		self.n = 1
		self.d = 1
		self.spread = None
		self.intervals = None

	def produce_intervals(self, n, d):
		drop = 0
		for i in range(1, d):
			#print "-----"
			#print n, i, d
			#print n * i, d
			#print n * i / d
			if n * i / d > drop: 
				drop += 1
				yield (self.rn, self.rd * 2)
			else:
				yield (self.rn, self.rd)
		
	def _init_spread(self):
		if self.spread is None:
			self.spread = [1 for i in range(1, self.c)]
			
	def _init_intervals(self):
		if self.intervals is None:
			self.intervals = []
			for interval in self.produce_intervals(self.v, self.c):
				self.intervals.append(interval)

	def log_ratio(self, rn, rd):
		import math
		return math.log(2.0 * rn / rd) / math.log(2.0)
		
	def note_ratio(self, rn, rd):
		return int(self.log_ratio(rn, rd) * self.c - self.c + .5)
		

	def _init_v(self):
		if self.v is None:
			self.v = self.note_ratio(self.rn, self.rd)
		
	def solve(self):
		i = 0
		best_n = self.n
		best_d = self.d
		best_diff = decimal.Decimal(1000)
		best_r = 1000
		while True:
			i += 1
			p = self.produce()

			for i in range(0, self.c):
				next(p)
			
			r = next(p)
			if i % 1000 == 0:
				print((r, self.n, self.d, best_r, best_n, best_d, abs(r - 2), best_diff))
				
			if abs(r - 2) < best_diff:
				best_n = self.n
				best_d = self.d
				best_diff = abs(r - 2)
				best_r = r
				if best_diff < decimal.Decimal(1) / 1000:
					print((best_n, best_d, best_r))
				
			if best_diff < goal:
				break
			elif r < 2:
				self.d += 1
			elif r > 2:
				self.n += 1

	def tuning(self):
		self._init_spread()
		self.total = sum(self.spread)
		self.pieces = [decimal.Decimal(cardinal) / self.total for cardinal in self.spread]
		if self.n == 1 and self.d == 1: 
			self.solve()
		p = self.produce()
		return dict((n, float(str(r)[:goal_digits + 1])) for n, r in zip(list(range(0, self.c + 1)), sorted(next(p) for i in range(0, self.c + 1))))

	def produce(self):
		self._init_v()
		self._init_intervals()
		r = decimal.Decimal("1.0")
		yield r
		while True:
			for part, (n, d) in zip(self.pieces, self.intervals):
				r = r * n / d - part * self.n / self.d
				yield r

comma_even = Comma()
comma_even.n = 2564
comma_even.d = 144579

even = comma_even.tuning()

comma_well = Comma()
comma_well.n = 640
comma_well.d = 35403
comma_well.spread = [1, 1, 1, 1, 0, 0, 0, 2, 2, 2, 2]

well = comma_well.tuning()

comma_even19 = Comma()
comma_even19.n = 5922
comma_even19.d = 55819
comma_even19.c = 19

even19 = comma_even19.tuning()

comma_well19 = Comma()
comma_well19.n = 6131
comma_well19.d = 46434
comma_well19.c = 19
comma_well19.spread = [1,1,1,1,1,1, 0,0,0,0,0,0,0, 2,2,2,2,2,2,2]

well19 = comma_well19.tuning()

comma_pyth19 = Comma()
comma_pyth19.n = 4117
comma_pyth19.d = 61007
comma_pyth19.c = 19
comma_pyth19.spread = [1,0,0,0,0,0, 0,0,0,0,0,0,0, 0,0,0,0,0,0,0]

pyth19 = comma_pyth19.tuning()

comma_even24 = Comma()
comma_even24.n = 1798
comma_even24.d = 49931
comma_even24.c = 24

even24 = comma_even24.tuning()

if __name__ == "__main__":
	import pprint
	#pprint.pprint(comma_even.intervals)
	#pprint.pprint(comma_even.spread)
	#pprint.pprint(even)
	#pprint.pprint(comma_well.intervals)
	#pprint.pprint(comma_well.spread)
	#pprint.pprint(well)
	pprint.pprint(comma_even19.intervals)
	pprint.pprint(comma_even19.spread)
	pprint.pprint(even19)
	pprint.pprint(comma_well19.intervals)
	pprint.pprint(comma_well19.spread)
	pprint.pprint(well19)
	pprint.pprint(comma_pyth19.intervals)
	pprint.pprint(comma_pyth19.spread)
	pprint.pprint(pyth19)
	#pprint.pprint(comma_even24.intervals)
	#pprint.pprint(comma_even24.spread)
	#pprint.pprint(even24)
	

