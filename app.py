from flask import Flask, render_template, request, redirect, url_for, flash, jsonify


#create an instance of Flask class with the name
#of the runnung application as the argument
app = Flask(__name__)



#import module for ORM
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database_setup import Base, University, Room, User


### Import and config for picture upload ####
import os
from werkzeug import secure_filename
UPLOAD_FOLDER = 'static/'
ALLOWED_EXTENSIONS = set(['txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif'])
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER 



#New Imports to help create anti-forgery state token
#login_session works like a dictionary
from flask import session as login_session
import random, string

#Imports for handling code sent back from the call back method
from oauth2client.client import flow_from_clientsecrets
from oauth2client.client import FlowExchangeError
import httplib2
import json
from flask import make_response
import requests

CLIENT_ID = json.loads(open('client_secrets.json', 'r').read())['web']['client_id']
#APPLICATION_NAME= "Got Room Application"

#create connection to database
engine = create_engine("sqlite:///gotroomwithusers.db")
Base.metadata.bind=engine
DBSession = sessionmaker(bind=engine)
session=DBSession()





#Create anti-forgery state token
@app.route('/login')
def showLogin():

  	state = ''.join(random.choice(string.ascii_uppercase + string.digits) for x in range(32))
  	login_session['state'] = state
  	#return "The current session state is %s" % login_session['state']
  	return render_template('login.html', STATE = state)


@app.route('/gconnect', methods=['POST'])
def gconnect():
	#Validate state token 
  	if request.args.get('state') != login_session['state']:
    		response = make_response(json.dumps('Invalid state parameter.'), 401)
    		response.headers['Content-Type'] = 'application/json'
    		return response
  	#Obtain authorization code, now compatible with Python3
  	request.get_data()
  	code = request.data.decode('utf-8')

  	try:

    		# Upgrade the authorization code into a credentials object
    		oauth_flow = flow_from_clientsecrets('client_secrets.json', scope='')
    		oauth_flow.redirect_uri = 'postmessage'
    		credentials = oauth_flow.step2_exchange(code)
  	except FlowExchangeError:
    		response = make_response(json.dumps('Failed to upgrade the authorization code.'), 401)
    		response.headers['Content-Type'] = 'application/json'
    		return response
  
  	# Check that the access token is valid.
  	access_token = credentials.access_token
  	url = ('https://www.googleapis.com/oauth2/v1/tokeninfo?access_token=%s'
         	% access_token)
  	# Submit request, parse response - Python3 compatible 
  	h = httplib2.Http()
  	response = h.request(url, 'GET')[1]
  	str_response = response.decode('utf-8')
  	result = json.loads(str_response)

  	# If there was an error in the access token info, abort.
  	if result.get('error') is not None:
    		response = make_response(json.dumps(result.get('error')), 500)
    		response.headers['Content-Type'] = 'application/json'

  	# Verify that the access token is used for the intended user.
  	gplus_id = credentials.id_token['sub']
  	if result['user_id'] != gplus_id:
    		response = make_response(json.dumps("Token's user ID doesn't match given user ID."), 401)
    		response.headers['Content-Type'] = 'application/json'
    		return response

  	# Verify that the access token is valid for this app.
  	if result['issued_to'] != CLIENT_ID:
    		response = make_response(json.dumps("Token's client ID does not match app's."), 401)
    		response.headers['Content-Type'] = 'application/json'
    		return response

  	stored_access_token = login_session.get('access_token')
  	stored_gplus_id = login_session.get('gplus_id')
  	if stored_access_token is not None and gplus_id == stored_gplus_id:
    		response = make_response(json.dumps('Current user is already connected.'),200)
    		response.headers['Content-Type'] = 'application/json'
    		return response
    
  	# Store the access token in the session for later use.
  	login_session['access_token'] = access_token
  	login_session['gplus_id'] = gplus_id
 
  
  	#Get user info
  	userinfo_url =  "https://www.googleapis.com/oauth2/v1/userinfo"
  	params = {'access_token': access_token, 'alt':'json'}
  	answer = requests.get(userinfo_url, params=params)
  
  	data = answer.json()

  	login_session['username'] = data['name']
  	login_session['picture'] = data['picture']
  	login_session['email'] = data['email']
 
  	#see if user exists, if it doesn't make a new one
  	user_id = getUserID(login_session['email'])
  	if not user_id:
    		user_id = createUser(login_session)
  	login_session['user_id'] = user_id


  	output = ''
  	output +='<h1>Welcome, '
  	output += login_session['username']
  	output += '!</h1>'
  	output += '<img src="'
  	output += login_session['picture']
  	output +=' " style = "width: 300px; height: 300px;border-radius: 150px;-webkit-border-radius: 150px;-moz-border-radius: 150px;"> '
  	flash("you are now logged in as %s"%login_session['username'])
  	return output

#User Helper Functions
def createUser(login_session):

  	newUser = User(name = login_session['username'], email = login_session['email'], picture = login_session['picture'])
  	session.add(newUser)
  	session.commit()
  	user = session.query(User).filter_by(email = login_session['email']).one()
  	return user.id

def getUserInfo(user_id):
  	user = session.query(User).filter_by(id = user_id).one()
  	return user

def getUserID(email):
  	try:
      		user = session.query(User).filter_by(email = email).one()
      		return user.id
  	except:
      		return None

#DISCONNECT - Revoke a current user's token and reset their login_session
@app.route('/gdisconnect')
def gdisconnect():

    	#Only disconnect a connected user.
  	access_token = login_session.get('access_token')
  	if access_token is None:
   		response = make_response(json.dumps('Current user not connected.'),401)
    		response.headers['Content-Type'] = 'application/json'
    		return response 
  	url = 'https://accounts.google.com/o/oauth2/revoke?token=%s' % access_token
  	h = httplib2.Http()
  	result = h.request(url, 'GET')[0]
  	if result['status'] == '200':
    		#Reset the user's sesson.
    		del login_session['access_token']
    		del login_session['gplus_id']
    		del login_session['username']
    		del login_session['email']
    		del login_session['picture']

    		response = make_response(json.dumps('Successfully disconnected.'), 200)
   		response.headers['Content-Type'] = 'application/json'
    		return response

  	else:
    		# For whatever reason, the given token was invalid.
    		response = make_response(json.dumps('Failed to revoke token for given user.', 400))
    		response.headers['Content-Type'] = 'application/json'
    		return response
    	

@app.route("/")
@app.route("/university")
def showUniversities():
	#get all universities from university table
	universities = session.query(University).all()
	if "username" not in login_session:
		return render_template("publicuniversities.html", universities=universities)
	else:
		return render_template("universities.html", universities=universities)


#add a new university
@app.route("/university/new/", methods=["GET", "POST"] )
def newUniversity():
	if "username" not in login_session:
		return redirect("login")
	if request.method == "POST" and request.form["newCity"] != "":
		newUniversity = University(name=request.form["newUni"], city=request.form["newCity"], user_id =login_session["user_id"])
		session.add(newUniversity)
		session.commit()

		#feedback to user
		flash("new university added")
		return redirect(url_for("showUniversities"))
	elif request.method == "POST" and request.form["newCity"] == "":
		flash("City Must Be Added")
		return redirect(url_for("newUniversity"))


	else:
		return render_template("newuni.html")
		

#edit an existing university
@app.route("/university/<int:university_id>/edit/", methods=["GET", "POST"])
def editUniversity(university_id):
	editedUni = session.query(University).filter_by(id=university_id).one()
	if "username" not in login_session:
		return redirect("login")

	#local permission check for logged in users to edit only their data
	if editedUni.user_id != login_session['user_id']:
		return "<script>function myFunction() {alert('You are not authorized to edit this university. Please create your own university in order to edit.');}</script><body onload='myFunction()''>"
	if request.method == "POST":
		if request.form["newEditedName"]:
			editedUni.name = request.form["newEditedName"]
		if request.form["newEditedCity"]:
			editedUni.city = request.form["newEditedCity"]
		session.add(editedUni)
		session.commit()

		#feedback to user
		flash("University Successfully Edited")

		return redirect(url_for("showUniversities"))
	else:
		return render_template("edituni.html", university=editedUni)


#delete an existing university
@app.route("/university/<int:university_id>/delete/", methods=["GET", "POST"])
def deleteUniversity(university_id):
	uniToDelete = session.query(University).filter_by(id=university_id).one()
	if "username" not in login_session:
		return redirect("login")

	#local permission check for logged in users to edit only their data
	if uniToDelete.user_id != login_session['user_id']:
		return "<script>function myFunction() {alert('You are not authorized to delete this university');}</script><body onload='myFunction()''>"


	if request.method == "POST":
		session.delete(uniToDelete)
		session.commit()

		#feedback to user
		flash("University Successfully Deleted")

		return redirect(url_for("showUniversities"))
	else:
		return render_template("deleteuni.html", university=uniToDelete)



#show rooms for a university
@app.route("/university/<int:university_id>/")
@app.route("/university/<int:university_id>/rooms/")
def showRooms(university_id):
	university = session.query(University).filter_by(id=university_id).one()
	rooms = session.query(Room).filter_by(university_id=university_id).all()
	room_poster = getUserInfo(university.user_id)

	if "username" not in login_session:
		return render_template("publicrooms.html", rooms=rooms, university=university, room_poster=room_poster)
	else:
		return render_template("rooms.html", rooms=rooms, university=university, room_poster=room_poster)


### Determine if the fileuploaded it's allowed ###
def allowed_file(filename):
    	return '.' in filename and \
           	filename.rsplit('.', 1)[1] in ALLOWED_EXTENSIONS 

#create a new room for a particular university
@app.route("/university/<int:university_id>/rooms/new/", methods=["GET", "POST"])
def newRoom(university_id):
	if "username" not in login_session:
		return redirect("login")

	#obtain the current university where user wants to add a room
	university = session.query(University).filter_by(id=university_id).one()

	if request.method == "POST":
		file = request.files['file']
		if file and allowed_file(file.filename):
			filename = secure_filename(file.filename)
			file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
		aNewRoom = Room(owner_name=request.form["ownerName"], size=request.form["roomSize"]\
				       , picture=filename, description=request.form["roomDescription"], price=request.form["roomPrice"]\
				        , address=request.form["adress"], owner_number=request.form["phoneNum"], \
				        university_id=university_id, user_id=login_session["user_id"])

		session.add(aNewRoom)
		session.commit()

		#feedback to user
		flash("New Room Created")		

		return redirect(url_for("showRooms", university_id=university_id))
	else:
		return render_template("newroom.html", university_id=university_id)

	


#edit a room in apartuclar university
@app.route("/university/<int:university_id>/<int:room_id>/edit/", methods=["GET", "POST"])
def editRoom(university_id, room_id):
	if "username" not in login_session:
		return redirect("login")
	roomToEdit = session.query(Room).filter_by(id=room_id).one()	
	university = session.query(University).filter_by(id=university_id).one()

	if login_session["user_id"] != roomToEdit .user_id:
		return "<script>function myFunction() {alert('You are not authorized to edit this room. Please create your own in order to edit items.');}</script><body onload='myFunction()''>"

	if request.method == "POST":
		if request.form["ownerName"]:
			roomToEdit.owner_name = request.form["ownerName"]
		if request.form["roomSize"]:
			roomToEdit.size = request.form["roomSize"]
		if request.form["roomDescription"]:
			roomToEdit.description = request.form["roomDescription"]
		if request.form["roomPrice"]:
			roomToEdit.price = request.form["roomPrice"]
		if request.form["adress"]:
			roomToEdit.address = request.form["adress"]
		if request.form["phoneNum"]:
			roomToEdit.owner_number = request.form["phoneNum"]
		session.add(roomToEdit)
		session.commit()

		#feedback to user
		flash("Room Successfully Edited")	

		return redirect(url_for("showRooms", university_id=university_id))
	else:
		return render_template("editroom.html", university_id=university_id, room_id=room_id, room=roomToEdit)

		

	return render_template("editroom.html", university_id=university_id, room_id=room_id, room=roomToEdit)


#delete a room 
@app.route("/university/<int:university_id>/<int:room_id>/delete/", methods=["GET", "POST"])
def deleteRoom(university_id, room_id):
	if "username" not in login_session:
		return redirect("login")

	roomToDelete = session.query(Room).filter_by(id=room_id).one()
	university = session.query(University).filter_by(id=university_id).one()
	room_poster = getUserID(login_session["email"])
	if login_session["user_id"] != roomToDelete.user_id:
		return "<script>function myFunction() {alert('You are not authorized to delete this room.');}</script><body onload='myFunction()''>"

	if request.method == "POST":
		#remove associated room picture while deleting a room
		os.remove(os.path.join(app.config['UPLOAD_FOLDER'], roomToDelete.picture))
		session.delete(roomToDelete)
		session.commit()

		#feedback to user
		flash("Room Successfully Deleted")	

		return redirect(url_for("showRooms", university_id=university_id))
	else:
		return render_template("deleteroom.html", university_id=university_id, room_id=room_id, room=roomToDelete)
	

#API Endpoints for GET Requests

#JSON data for list of all universitites
@app.route("/university/JSON/")
def showUniversitiesJSON():
	universities = session.query(University).all()
	return jsonify(universitites=[university.serialize for university in universities])


#JSON data for rooms in a university
@app.route("/university/<int:university_id>/rooms/JSON")
def showRoomsJSON(university_id):
	university = session.query(University).filter_by(id=university_id).one()
	rooms = session.query(Room).filter_by(university_id=university_id).all()
	return jsonify(rooms=[room.serialize for room in rooms])

#JSON data for a single room
@app.route("/university/<int:university_id>/rooms/<int:room_id>/JSON/")
def singleRoomJSON(university_id, room_id):
	university = session.query(University).filter_by(id=university_id).one()
	singleRoom = session.query(Room).filter_by(id=room_id).one()
	return jsonify(room=[singleRoom.serialize])



if __name__ == '__main__':
	app.secret_key = "super_secret_key"
	app.debug = True
	app.run("0.0.0.0", port=5000)