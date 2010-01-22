import datetime
import threading


class PeriodicScheduler(threading.Thread):
	defaultInterval = 3600
	items = []
	schedule = threading.Event()
	lock = threading.Lock()
	terminate = False

	def addTimer(self, callback, interval):
		if not interval:
			interval = self.defaultInterval

		self.lock.acquire()
		self.items.append({
			'nextCall' : datetime.datetime.now(),
			'interval' : interval,
			'callback' : callback,
		})
		self.lock.release()

		self.schedule.set()
	
	def run(self):
		self.scheduleTimer = None
		while True:

			# wait for events
			self.schedule.wait()

			print 'event! locking...'
			
			self.lock.acquire()

			print 'locked.'

			if self.terminate:
				if self.scheduleTimer:
					self.scheduleTimer.cancel()
				print 'terminated'
				self.lock.release()
				return


			# process timeouts
			now = datetime.datetime.now()

			nextTimeout = None
			for i in self.items:
				if i['nextCall'] < now:
					i['callback']()
					i['nextCall'] = now + i['interval']

				if nextTimeout:
					nextTimeout = min(nextTimeout, i['nextCall'])
				else:
					nextTimeout = i['nextCall']

			# schedule
			if nextTimeout:

				if not self.scheduleTimer:
					self.scheduleTimer = threading.Timer((nextTimeout - now).seconds + float((nextTimeout - now).microseconds) / 1000000, self.timeout)
					self.scheduleTimer.start()

			self.schedule.clear()
			self.lock.release()

			print 'unlocked.'

	def timeout(self):
		self.lock.acquire()
		self.schedule.set()
		self.scheduleTimer = None
		self.lock.release()

	def wakeUp(self):
		self.lock.acquire()
		self.schedule.set()
		self.lock.release()

	def stop(self):
		self.terminate = True

		self.wakeUp()

def every1s():
	print 'every 1s'
def every3s():
	print 'every 3s'
def every10s():
	print 'every 10s'

ps = PeriodicScheduler()
ps.start()

ps.addTimer(every1s, datetime.timedelta(seconds=1))
ps.addTimer(every3s, datetime.timedelta(seconds=3))
ps.addTimer(every10s, datetime.timedelta(seconds=10))


