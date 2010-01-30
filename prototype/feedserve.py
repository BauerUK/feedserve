import datetime
import threading
import pickle
import copy

import feedparser
import cherrypy

def dt(t):
	return datetime.datetime(year=t[0], month=t[1], day=t[2], hour=t[3], minute=t[4], second=t[5])

class Entry(object):
	pass

class Subscription(object):

	lock = threading.Lock()

	stateIdle = 0
	stateUpdating = 2 # the subscription is updating right now
	stateError = 3 # some error occured. TODO add more detail: 404, connection refused, timeout ..?
	
	def __init__(self, uri, lastUpdate = None):
		self.uri = uri
		self.lastUpdate = lastUpdate
		self.title = '???'
		self.entries = {}

		self.state = self.stateIdle

	def update(self):
		with self.lock:
			if self.state == self.stateUpdating:
				self.lock.release()
				raise ValueError('already updating')

			FeedDownloadWorker(self.uri, self.receiveData, self.receiveError).start()
			self.state = self.stateUpdating

	def receiveData(self, data):
		print 'got data. feed title = %s' % data.feed.title
		with self.lock:
			self.title = data.feed.title
			for entry in data.entries:
				e = Entry()
				e.title = entry.title
				e.uri = entry.link
				e.globalId = entry.id

				if 'published_parsed' in entry:
					e.time = max(dt(entry.published_parsed), dt(entry.updated_parsed))
				else:
					e.time = dt(entry.updated_parsed)

				e.read = False

				# make sure we keep the read status if there hasn't been any update
				if entry.id in self.entries:
					if self.entries[entry.id].time == e.time and self.entries[entry.id].read:
						e.read = True
				else:
					print 'new item %s' % e.title
				
				# update it anyway (title etc.)
				self.entries[entry.id] = e

			self.state = self.stateIdle
	
	def receiveError(self, data):
		print 'got error'

		with self.lock:
			self.state = self.stateError
	
	# return a "page" of entries, sorted by date
	def getPage(self, num=0):
		pageSize = 10
		
		with self.lock:
			entries = copy.deepcopy(self.entries.values())

		entries.sort(key=lambda x: x.time, reverse=True)

		return entries[num*pageSize:pageSize+1]
		



class FeedDownloadWorker(threading.Thread):
	def __init__(self, uri, dataCallback, errorCallback):
		threading.Thread.__init__(self, name='FeedDownloader')
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


class TestPage(object):
	def index(self):

		css = """
body {
	background-color: #eee;
}

.feedbox {
	float: left;
	width: 25em;
	font-family: sans-serif;
	font-size: 80%;
	background-color: white;
	border: 1px solid #aaa;
	margin: 1em;
}

.feedbox h3 {
	background-color: #aaa;
	color: white;
	margin: 0;
	padding: .5em;
}

.feedbox ul {
	list-style-type: square;
}

.feedbox ul li a:link {
	color: black;
	text-decoration: none;
}

.feedbox ul li a:visited {
	color: darkgray;
	text-decoration: none;
}

.feedbox ul li a:hover {
	background-color: #e7ffc9;
}
"""

		html = '<!doctype html>\n<html><head><title>feedserve.py</title><style>%s</style></head><body>' % css
		html += '<h1>Feeds</h1>'

		for sub in subs:

			html += '<div class="feedbox"><h3>%s</h3><ul>' % sub.title
			entries = sub.getPage()

			for e in entries:
				html += '<li><a href="%s">%s</a></li>' % (e.uri, e.title)

			html += '</ul></div>'

		html += '</body></html>'

		return html
	
	index.exposed = True


class SchedulerStopper(cherrypy.process.plugins.SimplePlugin):
	def stop(self):
		print 'SchedulerStopper'
		ps.stop()

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
		Subscription('http://www.spiegel.de/schlagzeilen/index.rss'),
	]


try:

	ps = PeriodicScheduler()
	ps.start()

	for s in subs:
		# reset updating state 
		s.state = s.stateIdle
		ps.addTimer(s.update, datetime.timedelta(seconds=1800))

#	print 'waiting 3 secs for feeds to load'
#	import time
#	time.sleep(3)

	stopper = SchedulerStopper(cherrypy.engine)
	stopper.subscribe()

	cherrypy.quickstart(TestPage())

finally:
	ps.stop()

# write subs db
pickle.dump(subs, open(dbfile, 'w'))
