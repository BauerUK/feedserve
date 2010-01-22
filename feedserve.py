import feedparser
import datetime
import threading


class Subscription(object):

	lock = threading.Lock()

	stateIdle = 0
	stateUpdating = 2 # the subscription is updating right now
	stateError = 3 # some error occured. TODO add more detail: 404, connection refused, timeout ..?
	
	def __init__(self, uri, lastUpdate = None):
		self.uri = uri
		self.lastUpdate = lastUpdate

		self.state = self.stateIdle

	def update(self):
		self.lock.acquire()

		if self.state == self.stateUpdating:
			self.lock.release()
			raise ValueError('already updating')

		FeedDownloadWorker(self.uri, self.receiveData, self.receiveError).start()
		self.state = self.stateUpdating

		self.lock.release()
	
	def receiveData(self, data):
		print 'got data. feed title = %s' % data.feed.title
		self.lock.acquire()

		self.state = self.stateIdle

		self.lock.release()
	
	def receiveError(self, data):
		print 'got error'
		self.lock.acquire()

		self.state = self.stateError

		self.lock.release()


class FeedDownloadWorker(threading.Thread):
	def __init__(self, uri, dataCallback, errorCallback):
		threading.Thread.__init__(self)
		self.dataCallback = dataCallback
		self.errorCallback = errorCallback
		self.uri = uri
	
	def run(self):
		data = feedparser.parse(self.uri)

		if data.bozo == 1:
			self.errorCallback(data)
		else:
			self.dataCallback(data)


class PeriodicScheduler(threading.Thread):
	items = []
	schedule = threading.Event()
	lock = threading.Lock()
	terminate = False

	def addTimer(self, callback, interval, delay=datetime.timedelta()):
		interval = self.defaultInterval

		self.lock.acquire()
		self.items.append({
			'nextCall' : datetime.datetime.now() + delay,
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
			print 'event!', datetime.datetime.now()

			self.lock.acquire()

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
				if self.scheduleTimer:
					self.scheduleTimer.cancel()

				self.scheduleTimer = threading.Timer((nextTimeout - now).seconds + float((nextTimeout - now).microseconds) / 1000000, self.timeout)
				self.scheduleTimer.start()


			self.schedule.clear()
			self.lock.release()


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


#s = Subscription('http://feedparser.org/docs/examples/atom10.xml')
#s.update()
