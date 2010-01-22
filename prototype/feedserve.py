import feedparser
import datetime
import threading
import pickle

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

	def __init__(self):
		threading.Thread.__init__(self, name='Scheduler')

	def addTimer(self, callback, interval, delay=datetime.timedelta()):
		with self.lock:
			self.items.append({
				'nextCall' : datetime.datetime.now() + delay,
				'interval' : interval,
				'callback' : callback,
			})

			self.schedule.set()
	
	def run(self):
		self.scheduleTimer = None
		while True:

			# wait for events
			self.schedule.wait()
			print 'event'

			with self.lock:
				if self.terminate:
					if self.scheduleTimer:
						self.scheduleTimer.cancel()
					print 'terminated'
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


	def timeout(self):
		with self.lock:
			self.schedule.set()
			self.scheduleTimer = None

	def stop(self):
		self.terminate = True

		with self.lock:
			self.schedule.set()




dbfile = 'subscriptions.db'

# load/create subs db
try:
	subs = pickle.load(open(dbfile))
	print 'loaded %d subscriptions from disk' % len(subs)
except IOError as e:
	print 'could not load subscriptions', str(e)
	print 'creating default database'
	subs = [
		Subscription('http://feedparser.org/docs/examples/atom10.xml'),
		Subscription('http://www.glassoforange.co.uk/?feed=atom'),
		Subscription('http://blog.lostpedia.com/feeds/posts/default?alt=rss'),
	]


try:

	ps = PeriodicScheduler()
	ps.start()

	for s in subs:
		# reset updating state 
		s.state = s.stateIdle
		ps.addTimer(s.update, datetime.timedelta(seconds=300))

	print 'waiting 3 secs for feeds to load'
	import time
	time.sleep(3)


finally:
	ps.stop()

# write subs db
pickle.dump(subs, open(dbfile, 'w'))
