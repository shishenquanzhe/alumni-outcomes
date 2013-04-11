import logging
import cgi
import webapp2
import json
import jinja2
import os
import oauth
import re

from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.api import urlfetch
from google.appengine.ext.webapp import util

from gaesessions import get_current_session

jinja_environment = jinja2.Environment(
	loader=jinja2.FileSystemLoader(os.path.dirname(__file__)))

API_KEY = "wFNJekVpDCJtRPFX812pQsJee-gt0zO4X5XmG6wcfSOSlLocxodAXNMbl0_hw3Vl"
API_SECRET = "daJDa6_8UcnGMw1yuq9TjoO_PMKukXMo8vEMo7Qv5J-G3SPgrAV0FqFCd0TNjQyG"
#API_KEY = "e3m3hhk13i99"
#API_SECRET = "i1vChLn1sxp5hjcP"
OAUTH_USER = "9597d89b-c2e1-46fe-b9fd-00fde4896c6a"
OAUTH_SECRET = "ef7c0dd9-55b3-4fd7-853c-89f6e65ca3b3"
RETURN_URL = "/oauth"

client = oauth.LinkedInClient(API_KEY, API_SECRET, RETURN_URL)

# holding onto user credentials
class User(db.Model):
	userid = db.StringProperty()
	uname = db.StringProperty()
	utoken = db.StringProperty()
	usecret = db.StringProperty()

# crawling jobs
class Template(db.Model):
	name = db.StringProperty()
	short = db.StringProperty()
	school = db.StringProperty()
	person_file = db.Text()
	created = db.DateTimeProperty(auto_now_add=True)

# people crawled / to be crawled
class Person(db.Model):
	first_name = db.StringProperty()
	last_name = db.StringProperty()
	is_crawled = db.BooleanProperty()
	n_results = db.IntegerProperty()
	crawled_first_name = db.StringProperty()
	crawled_last_name = db.StringProperty()
	industry = db.StringProperty()
	location = db.StringProperty()
	country = db.StringProperty()

# job positions people may hold
class Position(db.Model):
	title = db.StringProperty()
	company_name = db.StringProperty()

# Constructor for template
def template_key():
  """Constructs a Datastore key for a Template entity with default_template."""
  return db.Key.from_path('Template', 'default_template')


class MainPage(webapp2.RequestHandler):
	def get(self):
		session = get_current_session()

		fileloaded = 'false'
		is_crawled = 'false'
		newchecked = 'checked="checked"'
		oldchecked = ''
		newhidden = ''
		oldhidden = 'style="display:none"'

		# if error 
		ecode = self.request.get('ecode')
		if ecode == '400':
			errormsg = 'Input job name exists, please select another'
		else:
			errormsg = ''

		# if file has been loaded
		loadfile = self.request.get('loadfile')
		if loadfile:
			newchecked = ''
			oldchecked = 'checked="checked"'
			newhidden = 'style="display:none"'
			oldhidden = ''
			fileloaded = 'true'

		# if returning from OAuth
		crawled = self.request.get('crawled')
		if crawled:
			# doing this through AJAX for progress bar
			is_crawled = 'true'

		# if receiving ~~mystery delete query~~
		clearall = self.request.get('obliterate')
		if clearall:
			template_q = db.GqlQuery("SELECT * FROM Template WHERE ANCESTOR IS :1",template_key())
			for template in template_q:
				template.delete()

			person_q = db.GqlQuery("SELECT * FROM Person WHERE ANCESTOR IS :1",person_key())
			for person in person_q:
				person.delete()

			position_q = db.GqlQuery("SELECT * FROM Position WHERE ANCESTOR IS :1",position_key())
			for position in position_q:
				position.delete()

		templates = []
		template_q = db.GqlQuery("SELECT * FROM Template WHERE ANCESTOR IS :1",template_key())
		for template in template_q:
			temp = {'name':template.name,'short':template.short}
			templates.append(temp)

		template_values = {
			'errormsg': errormsg,
			'newchecked': newchecked,
			'oldchecked': oldchecked,
			'newhidden': newhidden,
			'oldhidden': oldhidden,
			'fileloaded': fileloaded,
			'crawled': is_crawled,
			'todisable': len(templates) == 0 and 'disabled="disabled"' or '',
			'templates': templates
		}

		template = jinja_environment.get_template('index.html')
		self.response.out.write(template.render(template_values))

class LoadContent(webapp2.RequestHandler):
	def post(self):
		session = get_current_session()

		func = self.request.get('func')
		if func == 'loadfile':
			# check template name doesn't already exist.
			template_name = self.request.get('template-name')
			template_q = db.GqlQuery("SELECT * FROM Template WHERE name=:1",template_name)
			exists = template_q.get()
			if exists:
				return self.redirect('/?ecode=400')

			# if it doesn't exist, put in session variable
			session['template'] = template_name

			template = Template(parent=template_key())
			template.name = template_name
			template.short = re.sub('[^a-z0-9]','',template_name.lower())
			template.school = re.sub('[^A-Za-z0-9]','',self.request.get('school-name'))
			template.person_file = self.request.get('template-file')
			template.put()

			# input lines of file into template
			for line in template.person_file.split('\n'):
				alum_input = line.split(',')
				if len(alum_input) < 2 or len(alum_input) > 3:
					continue

				lname_group = re.search('[A-Z][a-z]+',alum[0])
				fname_group = re.search('[A-Z][a-z]+',alum[1])
				alum = Person(parent=template)
				alum.first_name = fname_group.group(0)
				alum.last_name = lname_group.group(0)
				alum.put()

			return self.redirect('/?loadfile=True')

class InitOAuth(webapp2.RequestHandler):
	def post(self):
		session = get_current_session()
		session['template'] = self.request.get('template-to-load')
		client.callback_url = "%s/oauth" % self.request.host_url
		self.redirect(client.get_authorization_url())

class HandleOAuth(webapp2.RequestHandler):
	def get(self):
		session = get_current_session()
		# verify token
		if self.request.get('oauth_token'):
			auth_token = self.request.get("oauth_token")
			auth_verifier = self.request.get("oauth_verifier")
			user_info = client.get_user_info(auth_token, auth_verifier=auth_verifier)

			session['uid'] = user_info['id']

			# put user in db
			user_key = db.Key.from_path('User', session['uid'])
			user = User(parent=user_key)
			user.userid = user_info['id']
			user.uname = user_info['name']
			user.utoken = user_info['token']
			user.usecret = user_info['secret']
			user.put()

			#self.response.out.write(user_info)
			self.redirect('/?crawled=True')
		else:
			self.redirect('/?crawled=error')

# do crawl
class DoCrawl(webapp2.RequestHandler):
	def post(self):
		session = get_current_session()
		if not session.has_key('uid'):
			return self.response.out.write('ERR 401 Session ID missing')

		# for testing
		# params = {'first-name':'winter','last-name':'mason','school-name':'indiana'}

		# get school name
		if session['template']:
			template_q = db.GqlQuery("SELECT * FROM Template WHERE short=:1",session['template'])
			t_exists = template_q.get()
			if t_exists:
				school = t_exists.school
				t_name = t_exists.name
			else:
				return self.response.out.write("ERR 400 Template db error, DoCrawl: " + session['template'])
		else:
			return self.response.out.write("ERR 400 Template session error, DoCrawl")

		user_q = db.GqlQuery("SELECT * FROM User WHERE userid=:1",session['uid'])
		user = user_q.get()
		if user:
			# iterate through people in Template
			person_q = Person.all()
			person_q.filter("is_crawled =",0)
			person_q.ancestor(t_exists)
			npeople = int(self.request.get('limit')) or 10
			for person in person_q.run(limit=npeople):
				params = {'first-name':person.first_name,'last-name':person.last_name,'school-name':school}
				self.response.out.write(person.last_name)
				# request_url = "http://api.linkedin.com/v1/people-search"
				# result = client.make_request(url=request_url, 
				# 	token=user.utoken, 
				# 	secret=user.usecret,
				# 	additional_params=params)
				# # handle throttle limit 
				# return self.response.out.write(result.content)
		else:
			return self.response.out.write("ERR 402 No user!")
		
		


app = webapp2.WSGIApplication([('/', MainPage), 
	('/extras', LoadContent), 
	('/initoauth', InitOAuth), 
	('/oauth', HandleOAuth),  
	('/crawl', DoCrawl)], 
	debug=True)






