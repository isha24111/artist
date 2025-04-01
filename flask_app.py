from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import pyrebase, time
import firebase_admin
from firebase_admin import credentials, db, auth, firestore, storage
from werkzeug.utils import secure_filename
import random
import re

# Initialize Flask app
app = Flask(__name__, template_folder='templates', static_url_path='/static')
app.secret_key = 'mother/teresaa'  # Set a secret key for flash messages

# Initialize Firebase Admin SDK with your service account credentials
cred = credentials.Certificate("json/artist-7b214-firebase-adminsdk-kudkb-f915613ba9.json")
firebase_admin.initialize_app(cred, {
    'databaseURL': "https://artist-7b214-default-rtdb.firebaseio.com",
    "storageBucket": "artist-7b214.appspot.com"
})

# Firebase configuration
firebaseConfig = {
    "apiKey": "AIzaSyBo6NeFISaYCMwlzHuSHtEby2B00vY8ifs",
    "authDomain": "artist-7b214.firebaseapp.com",
    "databaseURL": "https://artist-7b214-default-rtdb.firebaseio.com",
    "projectId": "artist-7b214",
    "storageBucket": "artist-7b214.appspot.com",
    "messagingSenderId": "207737047540",
    "appId": "1:207737047540:web:9ff4c238c0670dac93d1a1"
}

firebase = pyrebase.initialize_app(firebaseConfig)
auth = firebase.auth()
db = firebase.database()
storage = firebase.storage()
# Initialize Firestore DB
firebase_db = firestore.client()

# Route for the home page
@app.route('/')
def index():
    highlights_ref = db.child('highlights').get()
    highlights = highlights_ref.val() if highlights_ref.each() else {}

    all_highlights = [(url, user.replace(',', '.')) for user, user_photos in highlights.items() for url in user_photos.values()]
    random.shuffle(all_highlights)

    user_highlights = []
    user_email = None
    if 'user' in session:
        user_email = session['user']['email']
        email_key = user_email.replace('.', ',')
        user_highlights = list(highlights.get(email_key, {}).values())

    return render_template('index.html', user_email=user_email, user_highlights=user_highlights, all_highlights=all_highlights)

# Route for the report page
@app.route('/report')
def report():
    if 'user' not in session:
        return redirect(url_for('signup'))

    photo_url = request.args.get('photo_url')
    artist_email = request.args.get('artist_email')
    return render_template('report.html', photo_url=photo_url, artist_email=artist_email)

# Route to handle report form submission
@app.route('/submit_report', methods=['POST'])
def submit_report():
    if 'user' not in session:
        return redirect(url_for('signup'))

    user_email = session['user']['email']
    photo_url = request.form['photo_url']
    artist_email = request.form['artist_email']
    reason = request.form['reason']
    timestamp = int(time.time())

    # Store the report in Firebase
    report_data = {
        'user_email': user_email,
        'photo_url': photo_url,
        'artist_email': artist_email,
        'reason': reason,
        'timestamp': timestamp
    }
    db.child('reports').push(report_data)
    return redirect(url_for('index'))


@app.route('/highlight_preview')
def highlight_preview():
    return render_template('highlight_preview.html')

@app.route('/abouts')
def abouts():
    return render_template('abouts.html')

@app.route('/upload_highlight', methods=['POST'])
def upload_highlight():
    if 'user' not in session:
        flash('You need to sign in first', 'error')
        return redirect(url_for('signin'))

    user_info = session['user']
    user_email = user_info['email']
    email_key = user_email.replace('.', ',')

    highlight_photo = request.files['highlight_photo']
    filename = secure_filename(highlight_photo.filename)
    unique_filename = f"{filename}_{int(time.time())}"
    storage_path = f"highlight_photos/{email_key}/{unique_filename}"
    storage.child(storage_path).put(highlight_photo)
    download_url = storage.child(storage_path).get_url(None)

    # Store the highlight under the user's email in the Realtime Database
    db.child('highlights').child(email_key).push(download_url)
    return redirect(url_for('index'))

@app.route('/delete-highlight', methods=['POST'])
def delete_highlight():
    data = request.get_json()
    photo_url = data['photo_url']
    if 'user' not in session:
        return jsonify({'success': False, 'error': 'Not authenticated'})

    user_email = session['user']['email']
    email_key = user_email.replace('.', ',')

    # Find and delete the photo from the database
    highlights_ref = db.child('highlights').child(email_key).get()
    photo_key = None
    for key, url in highlights_ref.val().items():
        if url == photo_url:
            photo_key = key
            break

    if photo_key:
        db.child('highlights').child(email_key).child(photo_key).remove()
        # Delete the photo from storage
        try:
            file_name = photo_url.split('%2F')[-1].split('?')[0]  # Extract the file name from the URL
            storage_path = f"highlight_photos/{email_key}/{file_name}"
            bucket = firebase_admin.storage.bucket()
            blob = bucket.blob(storage_path)
            blob.delete()
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})
    else:
        return jsonify({'success': False, 'error': 'Photo not found'})


# Regular expression for validating email
email_regex = re.compile(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$')
# Known email domains for further validation
valid_email_domains = ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "aol.com"]


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        # Validate email format
        if not email_regex.match(email):
            flash('Invalid email format! Please use a valid email address.', 'error')
            return redirect(url_for('signup'))

        # Validate email domain
        domain = email.split('@')[1]
        if domain not in valid_email_domains:
            flash('Invalid email domain!', 'error')
            return redirect(url_for('signup'))

        try:
            user = auth.create_user_with_email_and_password(email, password)
            try:
                user_ref = firebase_db.collection('users').document(user['localId'])
                user_ref.set({
                    'email': email,
                    # Add more user information as needed
                })
            except Exception as firestore_error:
                print("Firestore Error:", firestore_error)
                # Handle the Firestore error if needed, but still continue
            return redirect(url_for('signin'))
        except Exception as e:
            error_message = str(e)
            if 'EMAIL_EXISTS' in error_message:
                flash('Account already exists with this email!', 'error')
            elif 'WEAK_PASSWORD' in error_message:
                flash('Weak password! Make it strong.', 'error')
            elif 'INVALID_EMAIL' in error_message:
                flash('Invalid email! Please use a valid email address.', 'error')
            else:
                flash('An error occurred. Please try again.', 'error')
            return redirect(url_for('signup'))
    return render_template('signup.html')

# Sign In Route
@app.route('/signin', methods=['GET', 'POST'])
def signin():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        try:
            user = auth.sign_in_with_email_and_password(email, password)
            session['user'] = user
            return redirect(url_for('profile'))
        except Exception as e:
            error_message = str(e)
            if 'EMAIL_NOT_FOUND' in error_message:
                flash('Email not found. Please check your email address.', 'error')
            elif 'INVALID_PASSWORD' in error_message:
                flash('Invalid password. Please try again.', 'error')
            else:
                flash('An error occurred. Please try again.', 'error')
            return redirect(url_for('signin'))
    return render_template('signin.html')

@app.route('/forget-password', methods=['GET', 'POST'])
def forget_password():
    if request.method == 'POST':
        email = request.form['email']
        try:
            auth.send_password_reset_email(email)
            flash('Password reset email sent. Please check your email.', 'success')
            return redirect(url_for('signin'))
        except Exception as e:
            flash(str(e), 'error')
            return redirect(url_for('forget_password'))
    return render_template('forget_password.html')

# Log Out Route
@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('index'))

# Route for uploading photos
@app.route('/upload-photos', methods=['POST'])
def upload_photos():
    if 'user' not in session:
        return redirect(url_for('signin'))

    user_info = session['user']
    user_email = user_info['email']
    id_token = user_info['idToken']
    email_key = user_email.replace('.', ',')

    user_ref = db.child('users').child(email_key).get(token=id_token)
    user_data = user_ref.val()

    if user_data:
        photos = request.files.getlist('photos')

        if photos:
            photo_urls = []
            for photo in photos:
                filename = secure_filename(photo.filename)
                unique_filename = f"{filename}_{int(time.time())}"
                storage_path = f"profile_photos/{email_key}/{unique_filename}"
                storage_path = storage_path.replace('//', '/')
                storage.child(storage_path).put(photo)
                download_url = storage.child(storage_path).get_url(None)
                photo_urls.append(download_url)

            # Append new photos to existing photos if any
            existing_photos = user_data.get('photos', [])
            data_to_update = {'photos': existing_photos + photo_urls}

            update_user_profile(email_key, data_to_update, id_token)

    return redirect(url_for('profile'))



# Route for deleting photos
# Route for deleting photos
@app.route('/delete-photo', methods=['POST'])
def delete_photo():
    if 'user' not in session:
        return jsonify({'error': 'User not logged in'}), 403

    user_info = session['user']
    user_email = user_info['email']
    id_token = user_info['idToken']
    email_key = user_email.replace('.', ',')

    photo_url = request.json.get('photo_url')

    try:
        user_ref = db.child('users').child(email_key).get(token=id_token)
        user_data = user_ref.val()

        if user_data:
            existing_photos = user_data.get('photos', [])
            if photo_url in existing_photos:
                existing_photos.remove(photo_url)
                db.child('users').child(email_key).update({'photos': existing_photos}, token=id_token)

                # Extract the file name from the photo URL
                file_name = photo_url.split('%2F')[-1].split('?')[0]
                storage_path = f"profile_photos/{email_key}/{file_name}"

                # Add logging to verify the path
                print(f"Deleting file from storage path: {storage_path}")

                # Delete the photo from storage
                bucket = firebase_admin.storage.bucket()
                blob = bucket.blob(storage_path)
                blob.delete()

                return jsonify({'success': 'Photo deleted successfully'}), 200
            else:
                return jsonify({'error': 'Photo not found'}), 404
        else:
            return jsonify({'error': 'User profile not found'}), 404

    except Exception as e:
        print(f"Error deleting photo: {e}")
        return jsonify({'error': str(e)}), 500


# Function to upload profile picture to Firebase Storage within user-specific folder
def upload_profile_picture(user_email, profile_picture):
    try:
        # Generate a unique filename using the user's email
        filename = f"{user_email.replace('.', ',')}_profile_picture.jpg"

        # Upload the profile picture to Firebase Storage in the user's folder
        storage_path = f"profile_pictures/{user_email}/{filename}"  # Adjusted storage path
        # Check and remove consecutive slashes if present
        storage_path = storage_path.replace('//', '/')
        storage.child(storage_path).put(profile_picture)

        # Get the download URL for the uploaded file
        download_url = storage.child(storage_path).get_url(None)

        return download_url
    except Exception as e:
        print(f"Error uploading profile picture: {e}")
        return None

# Route for the upload photos page
@app.route('/upload-photos-page')
def upload_photos_page():
    return render_template('preview_photo.html')

# Function to update user profile information in Firebase
def update_user_profile(user_id, data_to_update, id_token):
    try:
        db.child('users').child(user_id).update(data_to_update, token=id_token)
        return True
    except Exception as e:
        print(f"Error updating user profile: {e}")
        return False


# Route for the user's profile page
@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user' not in session:
        return redirect(url_for('signin'))

    user_info = session['user']
    user_email = user_info['email']
    id_token = user_info['idToken']

    print(f"Debug: User Info from session: {user_info}")  # Debugging line

    try:
        user_ref = db.child('users').child(user_email.replace('.', ',')).get(token=id_token)
        user_data = user_ref.val()
        user_profile = user_data

        print(f"Debug: Fetched user_data: {user_data}")  # Debugging line
        print(f"Debug: Fetched User Profile: {user_profile}")  # Debugging line

    except Exception as e:
        print(f"Error fetching user data: {e}")
        user_profile = None

    return render_template('profilepage.html', user_profile=user_profile)


# Modify the route for the edit profile page
@app.route('/edit_profile', methods=['GET', 'POST'])
def edit_profile():
    if 'user' not in session:
        return redirect(url_for('signin'))

    user_info = session['user']
    user_email = user_info['email']
    id_token = user_info['idToken']

    print(f"Debug: User Info from session: {user_info}")  # Debugging line

    try:
        user_ref = db.child('users').child(user_email.replace('.', ',')).get(token=id_token)
        user_data = user_ref.val()
        user_profile = user_data

        print(f"Debug: Fetched user_data for edit: {user_data}")  # Debugging line

        if request.method == 'POST':
            name = request.form['name']
            description = request.form['description']
            profile_picture = request.files.get('profile_picture')

            profile_picture_url = user_profile.get('profile_picture') if user_profile else None
            if profile_picture:
                profile_picture_url = upload_profile_picture(user_email, profile_picture)
                if not profile_picture_url:
                    return redirect(url_for('edit_profile'))

            data_to_update = {
                'name': name,
                'description': description,
                'profile_picture': profile_picture_url
            }

            db.child('users').child(user_email.replace('.', ',')).update(data_to_update, token=id_token)
            return redirect(url_for('profile'))

        print(f"Debug: Fetched User Profile for Edit: {user_profile}")  # Debugging line

    except Exception as e:
        print(f"Error fetching user data: {e}")
        user_profile = None

    return render_template('editprofile.html', user_profile=user_profile)

# ----------------------------------------------Search--------------------------------------------
# Route for search form page
@app.route('/search_form')
def search_form():
    return render_template('search_form.html')

# Route for handling search request
@app.route('/search_artist', methods=['POST'])
def search_artist():
    if 'user' not in session:
        return redirect(url_for('signup'))
    artist_email = request.form['artist_email']
    # Redirect to the artist profile page with the email as a parameter
    return redirect(url_for('artist_profile', artist_email=artist_email))

# Route for artist profile page
@app.route('/artist_profile/<artist_email>')
def artist_profile(artist_email):
    try:
        # Replace '.' with ',' to match the Firebase key format
        email_key = artist_email.replace('.', ',')
        user_ref = db.child('users').child(email_key).get()
        user_data = user_ref.val()

        if user_data:
            return render_template('artist_profile.html', artist_email=artist_email, user_data=user_data)
        else:
            flash('Artist profile not found', 'error')
            return redirect(url_for('search_form'))
    except Exception as e:
        flash(str(e), 'error')
        return redirect(url_for('search_form'))


# About Us:
@app.route('/about-us')
def about_us():
    return render_template('aboutus.html')

# Run the Flask app
if __name__ == '__main__':
    app.run(debug=True)