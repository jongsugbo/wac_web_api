from flask import Flask, request, jsonify, url_for, send_file, render_template
import dbconnect
import bcrypt
import pymysql, pymysql.cursors, uuid
import simplejson as json
from datetime import datetime, timezone, timedelta
import pytz
import boto3
from flask_cors import CORS
import urllib.parse
import urllib.request
import json
import pymysql.cursors
from decimal import Decimal, getcontext
import re
#import httpx
import logging
import threading
import time
import re
#import pusher
from event_bus import EventBus
from handlers import handler_save_to_mysql

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import requests


# for Firebase Cloud Messaging
#import firebase_admin
#from firebase_admin import credentials, messaging

# for Socket.IO
from flask_socketio import SocketIO, send

# for google FCM
from google.oauth2 import service_account
import google.auth.transport.requests

import pusher

app = Flask(__name__)

# Enable CORS for all routes
CORS(app)
#CORS(app, resources={r"/*": {"origins": "https://main.d3dcpsxgz274zt.amplifyapp.com/"}})
socketio = SocketIO(app, cors_allowed_origins="*")
#socketio = SocketIO(app)

# Asana API configuration as Header - Vivant account
ASANA_API_TOKEN = "2/1208783688655876/1209012657903509:b8f7b06dca3870358c7911c101fa15df"
HEADERS = {
    "Authorization": f"Bearer {ASANA_API_TOKEN}",
    "Content-Type": "application/json",
}

PORTFOLIO_GID = "1209004121316102"
WORKSPACE_GID = "34545127171843"
POLL_INTERVAL = 60  # Poll every 1 minute
WEBHOOK_URL = "https://wacapi.appwardtech.com/asana-webhook-handler"

# Configure Pusher
#pusher_client = pusher.Pusher(
#    app_id='1918007',
#    key='10ee80d6ff6dc14c8eca',
#    secret='31cf20e3b1bc45113abc',
#    cluster='ap1',
#    ssl=True
#)

pusher_client = pusher.Pusher(
  app_id='1918009',
  key='f619b623476d07f02a6c',
  secret='6e2e9c20831a1fc8b41a',
  cluster='ap1',
  ssl=True
)

# Api key from Pushy
#PUSHY_API_KEY = "0606deaa314a5a773499d6e0a65c4cc8acc7c71b9b6cebb4ca1e8ced43b2f31d"
# In-memory storage for tokens (replace with a database for production use)


# Configure logging to write to a file
logging.basicConfig(
    level=logging.INFO,
    filename="app.log",
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

@app.route('/')
def home():
    logger.info("Hello, Madayaw UAT!")
    return "Hello, Madayaw UAT!"

# Initialize EventBus
event_bus = EventBus()

# Register handlers
event_bus.register_listener("save_to_mysql", handler_save_to_mysql)

# Store the last known projects in the portfolio
previous_projects = set()


#==== socket.io =====
# This event will be triggered when the client connects
@socketio.on('connect')
def handle_connect():
    logger.info("Client connected")
    send('You are connected!', broadcast=True)


# Endpoint to simulate sending a notification
@app.route('/send_notification')
def send_notification():
    # Simulate a new record being inserted into the database
    socketio.emit('notification', {'message': 'New record inserted!'})
    return "Notification Sent", 200
#==== end of socket.io =====


def send_fcm_notification(title, body, target_token):
    
    logger.info("entered send_fcm_notif1")

    SCOPES = ["https://www.googleapis.com/auth/firebase.messaging"]
    SERVICE_ACCOUNT_FILE = 'wac-project-2eeb9-bcac9868aa41.json'
    PROJECT_ID = 'wac-project-2eeb9'

    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    request = google.auth.transport.requests.Request()
    credentials.refresh(request)
    access_token = credentials.token

    logger.info("entered send_fcm_notif2")

    url = f"https://fcm.googleapis.com/v1/projects/{PROJECT_ID}/messages:send"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; UTF-8",
    }

    message = {
        "message": {
            "token": target_token,
            "notification": {
                "title": title,
                "body": body
            },
            "data": {
                "type": "refresh_inbox"
            }
        }
    }

    response = requests.post(url, headers=headers, json=message)

    logger.info("send fcm notification:")

    logger.info(response.status_code, response.text)


# Function to make HTTP requests using urllib
def make_request(url):
    try:
        request = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {ASANA_API_TOKEN}"}
        )
        with urllib.request.urlopen(request) as response:
            if response.status == 200:
                return json.load(response)
            else:
                logger.error(f"HTTP Error: {response.status}")
                return None
    except Exception as e:
        logger.error(f"Request failed: {e}")
        return None


# Function to check if the project is already subscribed and subscribe if not
def subscribe_to_project(project_gid):
    try:
        logger.info(f"Subscribing to project {project_gid}...")

        # Create the webhook to subscribe to the project
        url = "https://app.asana.com/api/1.0/webhooks"
        data = json.dumps({
            "data": {
                "resource": project_gid,
                "target": WEBHOOK_URL
            }
        }).encode("utf-8")

        request = urllib.request.Request(url, data=data, method="POST", headers={
            "Authorization": f"Bearer {ASANA_API_TOKEN}",
            "Content-Type": "application/json"
        })

        with urllib.request.urlopen(request) as response:
            # Log the status code
            logger.info(f"Response status: {response.status}")
            
            # Read the response body for more detailed error message
            response_body = response.read().decode("utf-8")
            logger.info(f"Response body: {response_body}")

            if response.status == 201:
                logger.info(f"Successfully subscribed to project {project_gid}.")
                #subscribed_projects.add(project_gid)  # Add to the subscribed list
                return True
            else:
                # Log the error details
                logger.error(f"Failed to subscribe to project {project_gid}: {response.status}")
                logger.error(f"Error details: {response_body}")
                return False

    except Exception as e:
        logger.error(f"Error subscribing to project {project_gid}: {e}")
        return False


# Polling function for detecting new projects and changes to existing projects
def poll_portfolio():
    global previous_projects, subscribed_projects, subscribed_projects_details

    conn = dbconnect.getConnection()
    cur = conn.cursor()

    try:
        # Fetch previous projects from the database
        logger.info("Fetching previous projects from the database...")
        sql_fetch_previous = """SELECT project_gid FROM work_orders WHERE org_code = 'V1E'"""
        cur.execute(sql_fetch_previous)
        db_projects = cur.fetchall()
    
        # Log the raw data to debug issues
        #logger.info(f"Fetched data: {db_projects}")
    
        if not db_projects:
            logger.warning("No previous projects found in the database.")
            previous_projects = set()
        else:
            # Filter out None values and create a set of project GIDs
            previous_projects = set(row["project_gid"] for row in db_projects if row["project_gid"] is not None)
            logger.info(f"Loaded {len(previous_projects)} previous projects.")

    except Exception as e:
        logger.error(f"Error fetching previous projects from the database: {e}")
        previous_projects = set()  # Default to an empty set

    finally:
        # Close the cursor after fetching
        if cur:
            cur.close()

    while True:
        try:
            # Establish new database connection within the loop
            conn = dbconnect.getConnection()
            cur = conn.cursor()

            logger.info("Polling Asana portfolio...")

            # Fetch portfolio projects
            url = f"https://app.asana.com/api/1.0/portfolios/{PORTFOLIO_GID}/items"
            response_data = make_request(url)

            if response_data:
                current_projects = set(item["gid"] for item in response_data["data"])

                # Detect newly added projects
                new_projects = current_projects - previous_projects

                if new_projects:
                    logger.info(f"New projects detected: {new_projects}")

                    for project_gid in new_projects:
                        project_name, project_description = fetch_project_details(project_gid)
                        logger.info(f"New Project: {project_name}, Description: {project_description}")

                        prefix = extract_prefix(project_name)
                        if prefix:
                            wr_id = int(prefix)
                        else:
                            wr_id = 0

                        try:
                            # SQL for inserting work order data
                            sql_insert_work_order = """
                                INSERT INTO work_orders (project_name, wr_id, created_datetime, status, project_gid, org_code)
                                VALUES (%s, %s, %s, %s, %s, %s)
                            """
                            data = (project_name, wr_id, timezone2(), 'New', project_gid, 'V1E')

                            cur.execute(sql_insert_work_order, data)

                            # Get the newly created work order ID
                            pk_id = cur.lastrowid

                            # Log the work order creation
                            logger.info(f"New work order created successfully: {pk_id}")

                        except Exception as e:
                            logger.error(f"Error creating new work order: {str(e)}")

                        # Add project details to `subscribed_projects_details`
                        #subscribed_projects_details[project_gid] = {
                        #    "name": project_name,
                        #    "description": project_description,
                        #}

                        # Subscribe to the new project
                        subscribe_to_project(project_gid)
                        #subscribed_projects.add(project_gid)

                    # Commit all changes
                    conn.commit()

                # Update `previous_projects` to include the current projects
                previous_projects = current_projects

        except Exception as e:
            logger.error(f"Error in polling: {e}")

        finally:
            # Close the database connection within the loop
            if cur:
                cur.close()
            if conn:
                conn.close()

        # Wait for the next poll
        time.sleep(POLL_INTERVAL)


# Fetch project details (name & description)
def fetch_project_details(project_gid):
    """Fetch project details, including the name and description."""
    try:
        url = f"https://app.asana.com/api/1.0/projects/{project_gid}"
        response_data = make_request(url)
        if response_data and "data" in response_data:
            project_name = response_data["data"].get("name", "Unknown Project")
            project_description = response_data["data"].get("notes", "No description")
            return project_name, project_description
    except Exception as e:
        logger.error(f"Error fetching project details for {project_gid}: {e}")
    return None, None

    
# Parse the prefix of project name
def extract_prefix(project_name):
    # Match text enclosed in square brackets
    match = re.match(r'\[(.*?)\]', project_name)
    if match:
        return match.group(1)  # Return the captured group inside the brackets
    return None  # Return None if no match is found
    

# Background thread to run polling
def start_polling():
    polling_thread = threading.Thread(target=poll_portfolio, daemon=True)
    polling_thread.start()

# Start polling on server startup
start_polling()


# Asana webhook handler for the subscription
@app.route('/asana-webhook-handler', methods=['POST'])
def asana_webhook_handler():
    logger.info("asana_webhook_handler called")
    try:
        # Handle X-Hook-Secret for Asana verification
        if 'X-Hook-Secret' in request.headers:
            return '', 200, {'X-Hook-Secret': request.headers['X-Hook-Secret']}
        
        # Parse the JSON payload
        payload = request.json
        if not payload:
            return jsonify({"error": "Invalid or missing JSON payload"}), 400

        # Log the payload for debugging
        logger.info(f"Payload received: {payload}")

        # Process the payload asynchronously (e.g., offload database insertion)
        handle_payload(payload)

        return jsonify({"status": "processed"}), 200

    except Exception as e:
        logger.error(f"Error: {e}")
        return jsonify({"error": "An error occurred while processing the webhook"}), 500


# Get project id from the payload
def get_project_id_from_payload(payload):
    """Extracts the project_id from the payload."""
    for event in payload.get("events", []):
        # Check if the resource type is a task
        if event.get("resource", {}).get("resource_type") == "task":
            task_id = event["resource"]["gid"]
            return fetch_project_id(task_id)
        # Check if the resource type is a project
        elif event.get("resource", {}).get("resource_type") == "project":
            return event["resource"]["gid"]
    return None


def fetch_project_id(task_id):
    """Fetches the project_id for a given task."""
    try:
        url = f"https://app.asana.com/api/1.0/tasks/{task_id}"
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req) as response:
            if response.status == 200:
                task_data = json.loads(response.read().decode())
                projects = task_data.get("data", {}).get("memberships", [])
                if projects:
                    return projects[0]["project"]["gid"]  # Assume the first project is the relevant one
            else:
                logger.error(f"Failed to fetch task details: {response.status}, {response.reason}")
    except Exception as e:
        logger.error(f"Error fetching project ID: {e}")

    return None


def get_project_sections(project_id):
    """Fetches all sections for a given project."""
    try:
        url = f"https://app.asana.com/api/1.0/projects/{project_id}/sections"
        req = urllib.request.Request(url, headers=HEADERS)
        
        with urllib.request.urlopen(req) as response:
            
            # Read and decode the response
            response_content = response.read().decode()

            if response.status == 200:
                sections_data = json.loads(response_content)
                sections = {
                    section["gid"]: section["name"]
                    for section in sections_data.get("data", [])
                }
                #logger.info("Sections:")
                #logger.info(sections)
                return sections
            else:
                logger.error(f"Failed to fetch sections: {response.status}, {response.reason}")
    except Exception as e:
        logger.error(f"Error fetching project sections: {e}")

    return {}
    
    
# Get custom field value
def fetch_custom_field_value(task_id, custom_field_name):
    """Fetches the value of a specific custom field for a given task."""
    try:
        url = f"https://app.asana.com/api/1.0/tasks/{task_id}"
        req = urllib.request.Request(url, headers=HEADERS)
        
        with urllib.request.urlopen(req) as response:
            if response.status == 200:
                task_data = json.loads(response.read().decode())
                custom_fields = task_data.get("data", {}).get("custom_fields", [])
                
                # Find the desired custom field by name
                for field in custom_fields:
                    if field.get("name") == custom_field_name:
                        return field.get("text")  # Use 'number' or 'enum_value' as needed
            else:
                print(f"Failed to fetch task details: {response.status}, {response.reason}")
    except Exception as e:
        print(f"Error fetching custom field value: {e}")

    return None


# get the old task_id and new project id for promoted task to project
def extract_task_and_project_ids(event_data):
    """Extract the old task ID and new project ID from event JSON."""
    old_task_id = None
    new_project_id = None

    for event in event_data.get("events", []):
        # Identify the old task ID
        if event["resource"]["resource_type"] == "task":
            old_task_id = event["resource"]["gid"]

        # Identify the new project ID
        if event["resource"]["resource_type"] == "project":
            new_project_id = event["resource"]["gid"]

    return old_task_id, new_project_id
    
# get task gid
def extract_single_task_gid(event_data):
    """Extracts the first task GID from the event data."""
    for event in event_data.get("events", []):
        if event["resource"]["resource_type"] == "task":
            return event["resource"]["gid"]  # Return the first task GID found
    return None  # Return None if no task GID is found


# Handle the payload
def handle_payload(payload):
    """Handles the incoming payload asynchronously."""
    try:
        # Database connection
        conn = dbconnect.getConnection()
        cur = conn.cursor()

        now = timezone2()

        # SQL for inserting log data
        sql_log = """
            INSERT INTO pm_events
            (log, posted_datetime)
            VALUES (%s, %s)
        """

        # Serialize payload details
        details = json.dumps(payload)
        posted_datetime = now

        log_data = (details, posted_datetime)

        # Insert log into pm_events table
        cur.execute(sql_log, log_data)
        conn.commit()

        # Process the payload events
        events = payload.get("events", [])
        for event in events:
            action = event.get("action")
            resource_type = event.get("resource", {}).get("resource_type")
            resource_subtype = event.get("resource", {}).get("resource_subtype")

            # Handle project updates
            project_id = get_project_id_from_payload(payload)
            logger.info("Project ID: ")
            logger.info(project_id)

            if project_id:
                # Fetch project name and description via API
                new_name, new_description = extract_project_details(project_id)
                logger.info("Fetched project details:")
                logger.info(f"Name: {new_name}")
                logger.info(f"Description: {new_description}")

                if new_name or new_description:
                    logger.info("Detected project updates.")

                    # Fetch current project data from database (if necessary)
                    sql_fetch_project = """
                        SELECT project_name, project_description
                        FROM work_orders
                        WHERE project_gid = %s
                    """
                    cur.execute(sql_fetch_project, (project_id,))
                    current_project = cur.fetchone()

                    if current_project:
                        current_name, current_description = current_project
                    else:
                        current_name, current_description = None, None

                    # Check and log changes
                    if new_name and new_name != current_name:
                        logger.info(f"Project name changed from '{current_name}' to '{new_name}'")

                        sql_update_name = """
                            UPDATE work_orders 
                            SET project_name = %s
                            WHERE project_gid = %s
                        """
                        cur.execute(sql_update_name, (new_name, project_id))
                        conn.commit()

                    if new_description and new_description != current_description:
                        logger.info(f"Project description changed from '{current_description}' to '{new_description}'")

                        sql_update_description = """
                            UPDATE work_orders 
                            SET project_description = %s
                            WHERE project_gid = %s
                        """
                        cur.execute(sql_update_description, (new_description, project_id))
                        conn.commit()

            # Process task movements for work request status updating
            if action == "added" and resource_type == "task":
                task_gid = extract_single_task_gid(payload)
                logger.info("Task ID: ")
                logger.info(task_gid)

                # Fetch sections dynamically for the task to check status changes
                sections = get_project_sections(project_id)
                section_id = event.get("parent", {}).get("gid")
                task_id = event.get("resource", {}).get("gid")

                logger.info("Section Name: " + sections.get(section_id, "Unknown"))

                sql_update_status = """
                    UPDATE work_requests
                    SET status = %s
                    WHERE wr_id = (
                        SELECT wr_id
                        FROM wr_pm_data
                        WHERE resource_type = 'Task' AND gid = %s
                    )
                """
                cur.execute(sql_update_status, (sections.get(section_id), task_id))
                conn.commit()

            # Process added comments
            if action == "added" and resource_type == "story" and resource_subtype == "comment_added":
                task_gid = event.get("parent", {}).get("gid")
                comment_gid = event.get("resource", {}).get("gid")

                logger.info(f"Processing comment on task {task_gid}...")

                # Fetch comment details via API
                comment_details = fetch_comment_details(comment_gid)
                if comment_details:
                    comment_text = comment_details.get("text")
                    created_at = now ##comment_details.get("created_at")
                    created_by = comment_details.get("created_by", {}).get("name")

                    logger.info(f"Captured comment: {comment_text} (Created by: {created_by} at {created_at})")

                    # SQL for inserting the comment into the database
                    sql_insert_comment = """
                        INSERT INTO task_comments
                        (task_gid, comment_gid, comment_text, created_at, created_by, org_code)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """
                    cur.execute(sql_insert_comment, (task_gid, comment_gid, comment_text, created_at, created_by, 'V1E'))
                    conn.commit()
                    
                    # Check if the comment is directed to @customer
                    if comment_text.strip().startswith("@customer"):
                        logger.info(f"Comment directed to customer: {comment_text}")

                        # Insert into app_inbox table
                        sql_insert_inbox = """
                            INSERT INTO app_inbox
                            (task_gid, comment_gid, message, created_datetime, created_by, source, org_code)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """
                        cur.execute(sql_insert_inbox, (task_gid, comment_gid, comment_text, created_at, created_by, 'asana', 'V1E'))
                        conn.commit()
                        
                        # Prepare data to send to Pusher
                        #data = {
                        #    'user_id': task_gid,
                        #    'message': comment_text,
                        #    'created_at': created_at
                        #}
                        
                        # Trigger a Pusher new message event to notify the wac app
                        #pusher_client.trigger('inbox-channel', 'new-message', data)
                        #logger.info("Event triggered: inbox-channel, new-message")
                        
                        # Send email notification
                        sql_fetch_wr =  """
                                        SELECT b.email_address AS email_address, b.project_location AS project_location, b.firstname AS firstname, b.lastname AS lastname, a.wr_id AS wr_id 
                                        FROM wr_pm_data a JOIN work_requests b ON a.wr_id = b.wr_id  
                                        WHERE a.gid = %s
                                        """
                        cur.execute(sql_fetch_wr, (task_gid,))
                        current_wr = cur.fetchone()
                        
                        if current_wr:
                            email_address = current_wr['email_address']
                            project_location = current_wr['project_location']
                            first_name = current_wr['firstname']
                            last_name = current_wr['lastname']
                            wr_id = current_wr['wr_id']
                        
                            send_email_notification(email_address, project_location, first_name, last_name, wr_id, comment_text)
                        else:
                            logger.error("No data found for the given task_gid.")
                            email_address, project_location, customer_name, wr_id = None, None, None, None
                        
                        unreadcount_notification(task_gid, wr_id)
                        
    except Exception as e:
        logger.error(f"Error while handling payload: {e}")

    finally:
        # Ensure connections are closed even on errors
        if cur:
            cur.close()
        if conn:
            conn.close()


# Fetch count of unread messages and notify wac app
def unreadcount_notification(task_gid, wr_id):
    try:
        # Database connection
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        # Fetch count of unread messages
        sql_fetch_unread =  """
                            SELECT COUNT(*) AS unread_count FROM app_inbox WHERE task_gid = %s AND read_datetime IS NULL  
                            """
        cur.execute(sql_fetch_unread, (task_gid,))
        current_unread = cur.fetchone()
        unread_count = current_unread['unread_count']
                        
        logger.info(f"unread message count: {unread_count}")
        
        # Prepare data to send to Pusher
        #countdata = {
        #    'wr_id': wr_id,
        #    'count': unread_count
        #}

        # Trigger a Pusher count unread event to notify the wac app
        #pusher_client.trigger('unreadcount-channel', 'count-unread', countdata)
        #logger.info("Event triggered: unreadcount-channel, count-unread")
        
    except Exception as e:
        logger.error(f"Failed to send unread messages count notification: {e}")
    

# Send email notification
def send_email_notification(email_address, project_location, first_name, last_name, wr_id, comment):
    """Sends an email notification for the work request update."""
    try:
        sender_email = "noreply@vivant1e.com"
        receiver_email = email_address.strip()  # Strip any whitespace
        password = "kucd ywmi bong cnps"  # Use environment variables in production
        
        # Remove @customer prefix from the comment
        if comment.startswith("@customer"):
            comment = comment[len("@customer"):].strip()
        
        # Validate email format
        if not re.match(r"[^@]+@[^@]+\.[^@]+", receiver_email):
            raise ValueError(f"Invalid email address: {receiver_email}")
        
        #logger.info(f"Sending email to: {receiver_email}")

        subject = "Comment from Vivant"
        body = (
            f"Dear {first_name},\n\n"
            f"We hope this message finds you well.\n\n"
            f"Please find below the recent comment from Vivant regarding your work request:\n\n"
            f"-----------------------------------\n"
            f"Comment:\n"
            f"\"{comment}\"\n"
            f"-----------------------------------\n\n"
            f"Here are the details of your work request:\n\n"
            f"Work Request Location: {project_location}\n"
            f"Customer Name: {first_name} {last_name}\n"
            f"Work Request No.: {wr_id}\n\n"
            f"Thank you for your attention to this matter.\n\n"
            f"Best regards,\n"
            f"Vivant Team"
        )

        # Set up the email message
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = receiver_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        # Connect to the email server and send the email
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, password)
            server.sendmail(sender_email, receiver_email, msg.as_string())

        #logger.info(f"Email notification sent to {receiver_email}.")
    except Exception as e:
        logger.error(f"Failed to send email notification: {e}")


# WAC send email facility for the approval notification
def wac_send_email_notification(email_address, reference_id, subject_title, action_title):
    
    try:    
        sender_email = "noreply@vivant1e.com"
        receiver_email = email_address.strip()  # Strip any whitespace
        password = "kucd ywmi bong cnps"  # Use environment variables in production
        
        # Validate email format
        if not re.match(r"[^@]+@[^@]+\.[^@]+", receiver_email):
            raise ValueError(f"Invalid email address: {receiver_email}")
        
        #logger.info(f"Sending email to: {receiver_email}")

        subject = subject_title
        body = (
            f"Hello,\n\n"
            f"This is to inform you that {reference_id} has been routed to you for {action_title}\n\n"
            f"Please review the details and take the appropriate action through the system at your earliest convenience.\n\n"
            f"Thank you,\n"
            f"Work and Cost Management System\n\n"
            f"Automated Notification - Please do not reply to this email."
        )

        # Set up the email message
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = receiver_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        # Connect to the email server and send the email
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, password)
            server.sendmail(sender_email, receiver_email, msg.as_string())

        #logger.info(f"Email notification sent to {receiver_email}.")
    except Exception as e:
        logger.error(f"Failed to send email notification: {e}")


# WAC send email facility for the work order has been approved notification
def wac_approved_send_email_notification(email_address, reference_id, subject_title, action_title):
    
    try:    
        sender_email = "noreply@vivant1e.com"
        receiver_email = email_address.strip()  # Strip any whitespace
        password = "kucd ywmi bong cnps"  # Use environment variables in production
        
        # Validate email format
        if not re.match(r"[^@]+@[^@]+\.[^@]+", receiver_email):
            raise ValueError(f"Invalid email address: {receiver_email}")
        
        #logger.info(f"Sending email to: {receiver_email}")

        subject = subject_title
        body = (
            f"Hello,\n\n"
            f"{reference_id} has been {action_title}.\n\n"
            f"Please Please refer to the system for further details.\n\n"
            f"Thank you,\n"
            f"Work and Cost Management System\n\n"
            f"Automated Notification - Please do not reply to this email."
        )

        # Set up the email message
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = receiver_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        # Connect to the email server and send the email
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, password)
            server.sendmail(sender_email, receiver_email, msg.as_string())

        #logger.info(f"Email notification sent to {receiver_email}.")
    except Exception as e:
        logger.error(f"Failed to send email notification: {e}")


# fetch comment details
def fetch_comment_details(comment_gid):
    """Fetches the details of a comment using the Asana API."""
    try:
        url = f"https://app.asana.com/api/1.0/stories/{comment_gid}"
        request = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {ASANA_API_TOKEN}"
        })
        with urllib.request.urlopen(request) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                return data.get("data")
            else:
                logger.error(f"Failed to fetch comment details. Status: {response.status}")
                return None
    except Exception as e:
        logger.error(f"Error fetching comment details for GID {comment_gid}: {e}")
        return None


# extract project details
def extract_project_details(project_id):
    """Fetches project details (name and description) using the project ID."""
    url = f"https://app.asana.com/api/1.0/projects/{project_id}"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req) as response:
            if response.status == 200:
                project_data = json.loads(response.read().decode())
                project_info = project_data.get("data", {})
                new_name = project_info.get("name")
                new_description = project_info.get("notes")
                return new_name, new_description
    except Exception as e:
        logger.error(f"Error fetching project details: {e}")
    
    return None, None


@app.route("/triggerevent", methods=["POST"])
def triggerevent():
    """API endpoint to trigger an event."""
    data = request.json
    event_name = data.get("event_name")
    payload = data.get("payload")
    
    if not event_name or not payload:
        return jsonify({"error": "Invalid input"}), 400

    # Process the event
    responses = event_bus.emit_event(event_name, payload)

    # Return the response along with the result from the event handler
    return jsonify({
        "message": f"Event '{event_name}' triggered successfully.",
        "responses": responses
    })


#--- get server date & time ----#
#@app.route('/timezone2', methods=['GET'])
def timezone2():
    
    try:
        tz = pytz.timezone('UTC')
        now = datetime.now(tz) + timedelta(hours = 8)

        formatted_datetime = now.strftime('%Y-%m-%d %H:%M:%S') 
        
        return formatted_datetime
        #app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        #return jsonify({"results" : formatted_datetime})
        
    except Exception as e:
        return(str(e))        
        

#--- authenticate user login ----#
@app.route('/userauth', methods=['GET'])
def userauth():
    if 'user_email' in request.args:
        user_email = request.args['user_email']
    else:
        return "Error: No Email Address field provided. Please specify it."
        
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT auth_channel, password, member_id FROM users WHERE email_address = %s"""
        data1 = (user_email) 
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Check if there are users
        if result:
            return jsonify({
                "message": "Users retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No users found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve users",
            "error": str(e)
        }), 500
 

#--- authenticate user google login ----#
@app.route('/usergoogleauth', methods=['GET'])
def usergoogleauth():
    if 'user_email' in request.args:
        user_email = request.args['user_email']
    else:
        return "Error: No Email Address field provided. Please specify it."
        
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT auth_channel, member_id FROM users WHERE email_address = %s"""
        data1 = (user_email) 
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Check if there are users
        if result:
            return jsonify({
                "message": "Users retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No users found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve users",
            "error": str(e)
        }), 500
        

#--- get user's information ----#
@app.route('/getuserinfo', methods=['GET'])
def getuserinfo():
    if 'user_email' in request.args:
        user_email = request.args['user_email']
    else:
        return "Error: No User Email field provided. Please specify it."
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT a.user_id AS user_id, a.email_address AS email_address, a.profile_photo AS profile_photo, a.personnel_id AS personnel_id, a.active AS active, a.device_id AS device_id, CONCAT(b.firstname,' ',b.middlename,' ',b.lastname) AS fullname FROM users a LEFT JOIN personnel b ON a.personnel_id = b.personnel_id WHERE a.email_address = %s"""
        data1 = (user_email)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Check if there are users
        if result:
            return jsonify({
                "message": "Users retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No users found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve users",
            "error": str(e)
        }), 500


#--- get all users ----#
@app.route('/getuserslist', methods=['GET'])
def getuserslist():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT * FROM app_users WHERE org_code = %s"""
        data1 = (org_code)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Check if there are users
        if result:
            return jsonify({
                "message": "Users retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No users found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve users",
            "error": str(e)
        }), 500


#--- get all roles ----#
@app.route('/getroleslist', methods=['GET'])
def getroleslist():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT * FROM app_roles WHERE org_code = %s"""
        data1 = (org_code)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Check if there are users
        if result:
            return jsonify({
                "message": "Roles retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No roles found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve roles",
            "error": str(e)
        }), 500


#--- get all roles per user ----#
@app.route('/getuserroleslist', methods=['GET'])
def getuserroleslist():
    if 'user_name' in request.args:
        user_name = request.args['user_name']
    else:
        return "Error: No User Name field provided. Please specify it."
    
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT * FROM app_user_roles WHERE user = %s AND org_code = %s"""
        data1 = (user_name, org_code)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Check if there are users
        if result:
            return jsonify({
                "message": "Roles retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No roles found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve roles",
            "error": str(e)
        }), 500
    

#--- upload file to AWS S3 bucket----#
@app.route('/uploadwacfile', methods=['POST'])
def uploadwacfile():
    file = request.files['file']
    file_name = file.filename
    
    try:
        conn = dbconnect.getS3Connection()
        conn.upload_fileobj(file, 'vivant-wac-uat', file_name)
        
        # Get the URL of the uploaded file
        #url = f"https://policetrack-images.s3.ap-southeast-1.amazonaws.com/{file_name}"
        url = file_name
        
        result = {
            'url': url
        }
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 201 status code
        return jsonify({"message": "File uploadd successfully", "result": result}), 201
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500


#--- save new customer ----#
@app.route('/postcustomer', methods=['POST'])
def postcustomer():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        now = timezone2()
        
        logger.info("new customer: ")
        logger.info(passed_data)
        
        hashed_pw = ""

        if passed_data.get("built_in_password"):
            raw_password = passed_data["built_in_password"]
            hashed_pw = hash_password(raw_password)
        
        # SQL for inserting record into customers
        sql1 = """INSERT INTO customers (firstname, middlename, lastname, email_address,  contact_number, street_address, city, province, company_name, org_code, created_datetime) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
        data1 = (passed_data["firstname"], passed_data["middlename"], passed_data["lastname"], passed_data["email_address"],  passed_data["contact_number"], passed_data["street_address"], passed_data["city"], passed_data["province"], passed_data["company_name"], passed_data["org_code"], now)
        
        cur.execute(sql1, data1)
        
        # Get the newly created customer id
        customer_id = cur.lastrowid
        
        # SQL for inserting record into app_users
        sql1 = """INSERT INTO app_users (user, built_in, built_in_password, oauth, status, firstname, lastname, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"""
        data1 = (passed_data["email_address"], passed_data["built_in"], hashed_pw, passed_data["oauth"], 1, passed_data["firstname"], passed_data["lastname"], passed_data["org_code"])
        
        cur.execute(sql1, data1)
        
        # SQL for inserting record into app_user_roles
        #sql1 = """INSERT INTO app_user_roles (user, role, status, org_code) VALUES (%s, %s, %s, #%s)"""
        #data1 = (passed_data["email_address"], passed_data["role"], 1,  passed_data["org_code"])
        
        #cur.execute(sql1, data1)
        
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 201 status code
        return jsonify({"message": "New Customer created successfully", "result": "created"}), 201
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        logger.error(str(e))
        return jsonify({"error": "Internal server error"}), 500


#--- save new work request ----#
@app.route('/postworkrequest', methods=['POST'])
def postworkrequest():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        now = timezone2()
        
        # SQL for inserting work request data
        sql1 = """INSERT INTO work_requests (firstname, middlename, lastname, email_address, customer_type, business_unit, project_location, proposal_deadline, job_start_date, job_end_date, project_desc, project_details, submitted_datetime, status, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
        data1 = (passed_data["firstname"], passed_data["middlename"], passed_data["lastname"], passed_data["email_address"], passed_data["customer_type"], passed_data["business_unit"], passed_data["project_location"], passed_data["proposal_deadline"], passed_data["job_start_date"], passed_data["job_end_date"], passed_data["project_desc"], passed_data["project_details"], now, passed_data["status"], passed_data["org_code"])
        
        cur.execute(sql1, data1)
        
        # Get the newly created work request id
        wr_id = cur.lastrowid
        
        # SQL for inserting requested services
        insert_services = """INSERT INTO requested_services (wr_id, service_id, detail_id, org_code) VALUES (%s, %s, %s, %s)"""
        
        # Process each parent and its children
        for parent in passed_data["services"]:
            parent_id = parent.get("parent_id")
            children = parent.get("children", [])

            # Insert the parent with no child if `children` is empty
            if not children:
                cur.execute(insert_services, (wr_id, parent_id, 0, passed_data["org_code"]))

            # Insert each child
            for child in children:
                child_id = child.get("child_id")
                cur.execute(insert_services, (wr_id, parent_id, child_id, passed_data["org_code"]))
        
        # SQL for updating remarks
        update_remarks = """UPDATE requested_services SET remarks = %s WHERE service_id = %s AND detail_id = %s AND wr_id = %s"""

        # Process the remarks list
        for remark in passed_data["remarkslist"]:
            service_id = remark.get("service_id")
            detail_id = remark.get("detail_id")
            remarkdata = remark.get("remarks")

            cur.execute(update_remarks, (remarkdata, service_id, detail_id, wr_id))
                
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 201 status code
        return jsonify({"message": "New Request created successfully", "result": wr_id}), 201
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500


#--- save work request changes ----#
@app.route('/updateworkrequest', methods=['POST'])
def updateworkrequest():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        wr_id = int(passed_data["wr_id"])
        
        now = timezone2()
        
        # SQL for inserting work request data
        sql1 = """UPDATE work_requests SET firstname = %s, middlename = %s, lastname = %s, email_address = %s, customer_type = %s, business_unit = %s, project_location = %s, proposal_deadline = %s, job_start_date = %s, job_end_date = %s, project_desc = %s, project_details = %s, submitted_datetime = %s, status = %s, org_code = %s WHERE wr_id = %s"""
        data1 = (passed_data["firstname"], passed_data["middlename"], passed_data["lastname"], passed_data["email_address"], passed_data["customer_type"], passed_data["business_unit"], passed_data["project_location"], passed_data["proposal_deadline"], passed_data["job_start_date"], passed_data["job_end_date"], passed_data["project_desc"], passed_data["project_details"], now, passed_data["status"], passed_data["org_code"], wr_id)
        cur.execute(sql1, data1)
        
        
        # SQL for deleting requested services
        delete_services = """DELETE FROM requested_services WHERE wr_id = %s"""
        cur.execute(delete_services, wr_id)
        
        
        # SQL for inserting requested services
        insert_services = """INSERT INTO requested_services (wr_id, service_id, detail_id, org_code) VALUES (%s, %s, %s, %s)"""
        
        # Process each parent and its children
        for parent in passed_data["services"]:
            parent_id = parent.get("parent_id")
            children = parent.get("children", [])

            # Insert the parent with no child if `children` is empty
            if not children:
                cur.execute(insert_services, (wr_id, parent_id, 0, passed_data["org_code"]))

            # Insert each child
            for child in children:
                child_id = child.get("child_id")
                cur.execute(insert_services, (wr_id, parent_id, child_id, passed_data["org_code"]))
        
        
        # SQL for updating remarks
        update_remarks = """UPDATE requested_services SET remarks = %s WHERE service_id = %s AND detail_id = %s AND wr_id = %s"""

        # Process the remarks list
        for remark in passed_data["remarkslist"]:
            service_id = remark.get("service_id")
            detail_id = remark.get("detail_id")
            remarkdata = remark.get("remarks")

            cur.execute(update_remarks, (remarkdata, service_id, detail_id, wr_id))
        
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 201 status code
        return jsonify({"message": "Request changes saved successfully", "result": "updated"}), 201
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500


#--- save work request status ----#
@app.route('/updateworkrequeststatus', methods=['POST'])
def updateworkrequeststatus():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        now = timezone2()
        wo_number = 0
        
        sql1 = """UPDATE work_requests SET status = %s WHERE wr_id = %s AND org_code = %s"""
        data1 = (passed_data["status_code"], passed_data["wr_id"], passed_data["org_code"])
        
        cur.execute(sql1, data1)
        
        #--- if work request status is Accepted ---
        if passed_data["status_code"] == "Accepted":
            # SQL for checking if a record exists
            check_wo = """SELECT COUNT(*) AS count FROM work_orders  
                      WHERE wr_id = %s AND org_code = %s"""
                      
            insert_wo = """INSERT INTO work_orders (status, job_start_date, job_end_date, project_description, location, business_unit, requested_by, created_datetime, wr_id, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
            
            update_wo = """UPDATE work_orders SET status = %s, job_start_date = %s, job_end_date = %s, project_description = %s, location = %s, business_unit = %s, created_datetime = %s WHERE wr_id = %s AND org_code = %s"""
            
            # Check if the record exists
            cur.execute(check_wo, (passed_data["wr_id"], passed_data["org_code"]))
            result = cur.fetchall()

            if result and "count" in result[0]:
                count = result[0]["count"]
                exists = count > 0
            else:
                exists = False

            if exists:
                # Update the existing record
                cur.execute(update_wo, (passed_data["wo_status"], passed_data["job_start_date"], passed_data["job_end_date"], passed_data["project_description"], passed_data["location"], passed_data["business_unit"], now, passed_data["wr_id"], passed_data["org_code"]
                ))
            else:
                # Insert a new record
                cur.execute(insert_wo, (passed_data["wo_status"], passed_data["job_start_date"], passed_data["job_end_date"], passed_data["project_description"], passed_data["location"], passed_data["business_unit"], passed_data["requested_by"], now, passed_data["wr_id"], passed_data["org_code"]
                ))
            
                # Get the newly created work order number
                wo_number = cur.lastrowid

                subjectTitle = f"Work Request {passed_data['wr_id']} - Accepted"
                referenceTitle = f"Work Request {passed_data['wr_id']}"
                actionTitle = f"accepted. A new Work Order {wo_number} has been generated automatically"

                wac_approved_send_email_notification(passed_data["requested_by"], referenceTitle, subjectTitle, actionTitle)
        
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 201 status code
        return jsonify({"message": "Status updated", "result": wo_number}), 201
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500


#--- save new work request attachments ----#
@app.route('/postwrattachments', methods=['POST'])
def postwrattachments():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        now = timezone2()
        
        # SQL for inserting attachments
        insert_attachment = """INSERT INTO wr_attachments (wr_id, file, org_code) VALUES (%s, %s, %s)"""

        # Process attachments array
        for filenme in passed_data["attachments"]:
            cur.execute(insert_attachment, (passed_data["wr_id"], filenme, passed_data["org_code"]))

        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 201 status code
        return jsonify({"message": "New Request File Attachments created successfully", "result": "Ok"}), 201
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500


#--- save response output of work management platform ----#
@app.route('/postworkmgtresponse', methods=['POST'])
def postworkmgtresponse():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        now = timezone2()
        
        # SQL for inserting work request data
        sql1 = """INSERT INTO wr_pm_data (wr_id, resource_type, gid, details, org_code, posted_datetime) VALUES (%s, %s, %s, %s, %s, %s)"""
        data1 = (passed_data["wr_id"], passed_data["resource_type"], passed_data["gid"], passed_data["details"], passed_data["org_code"], now)
        
        cur.execute(sql1, data1)
        
        # Get the newly created primary key id
        pk_id = cur.lastrowid
        
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 201 status code
        return jsonify({"message": "New Request created successfully", "result": pk_id}), 201
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500

# update app inbox for messages have been read
@app.route('/updatemessageread', methods=['PUT'])
def updatemessageread():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        now = timezone2()  # Ensure this function returns the current datetime
        
        # SQL for updating read datetime in app_inbox
        sql1 = """UPDATE app_inbox SET read_datetime = %s WHERE task_gid = %s AND read_datetime IS NULL"""
        data1 = (now, passed_data["task_gid"])  
        
        cur.execute(sql1, data1)
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 200 status code
        return jsonify({"message": "Updated successfully", "result": "updated"}), 200
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500


# update app inbox for messages have been read by the user
@app.route('/updatemessagereaduser', methods=['PUT'])
def updatemessagereaduser():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        now = timezone2()  # Ensure this function returns the current datetime
        
        # SQL for updating read datetime in app_inbox
        sql1 = """UPDATE app_inbox SET status = %s, read_datetime = %s WHERE recipient = %s AND status = %s"""
        data1 = ('read', now, passed_data["user_login"], 'unread')  
        
        cur.execute(sql1, data1)
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 200 status code
        return jsonify({"message": "Updated successfully", "result": "updated"}), 200
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500


# update approval request
@app.route('/updateapproval', methods=['PUT'])
def updateapproval():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        now = timezone2()  # Ensure this function returns the current datetime
        
        sql1 = """UPDATE approval_requests SET acted_by = %s, acted_datetime = %s, comment = %s, action_status = %s WHERE id = %s AND org_code = %s"""
        data1 = (passed_data["acted_by"], now, passed_data["comment"], passed_data["action_status"], passed_data["id"], passed_data["org_code"]) 
    
        cur.execute(sql1, data1)
        
        if passed_data["txn_type"] == "Work Order":
            sql1 = """UPDATE work_orders SET status = %s, cost_type_used = %s WHERE wo_number = %s AND org_code = %s"""
            data1 = (passed_data["action_status"], passed_data["cost_type"], passed_data["txn_reference"], passed_data["org_code"])
            
            cur.execute(sql1, data1)

            #--- get owner email address for notification
            if passed_data["action_status"] == "Approved":
                sql2 = """SELECT requested_by FROM work_orders WHERE wo_number = %s AND org_code = %s"""
                data2 = (passed_data["txn_reference"], passed_data["org_code"])
                
                cur.execute(sql2, data2)
                createdBy = cur.fetchall()
                createdByEmail = createdBy[0]['requested_by']
                subjectTitle = f"{passed_data['txn_type']} {passed_data['txn_reference']} - Approved"
                referenceTitle = f"{passed_data['txn_type']} {passed_data['txn_reference']}"
                actionTitle = "approved"
                
                wac_approved_send_email_notification(createdByEmail, referenceTitle, subjectTitle, actionTitle)

        if passed_data["txn_type"] == "Work Request":
            sql1 = """UPDATE work_requests SET status = %s WHERE wr_id = %s AND org_code = %s"""
            data1 = (passed_data["action_status"], passed_data["txn_reference"], passed_data["org_code"])
            
            cur.execute(sql1, data1)
        
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()

        pusher_client.trigger('inbox-channel', 'new-message', {'refresh': True})
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 200 status code
        return jsonify({"message": "Updated successfully", "result": "updated"}), 200
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500


# update approval request
@app.route('/submitcostestimate', methods=['POST'])
def submitcostestimate():
    passed_data = request.get_json()

    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()

        now = timezone2()  # Ensure this function returns the current datetime

        # Insert approval request
        sql1 = """
            INSERT INTO approval_requests 
            (txn_type, txn_reference, description, approval_type, requested_by, requested_datetime, org_code) 
            VALUES (%s, %s, %s, %s, %s, %s, %s)"""
        data1 = (
            passed_data["txn_type"],
            passed_data["txn_reference"],
            passed_data["description"],
            passed_data["approval_type"],
            passed_data["requested_by"],
            now,
            passed_data["org_code"]
        )
        cur.execute(sql1, data1)

        # If transaction type is Work Order, update work_orders table
        if passed_data["txn_type"] == "Work Order":
            sql2 = """
                UPDATE work_orders 
                SET status = %s 
                WHERE wo_number = %s AND org_code = %s"""
            data2 = (
                passed_data["approval_type"],
                passed_data["txn_reference"],
                passed_data["org_code"]
            )
            cur.execute(sql2, data2)

        # Notify users for first pre-approval
        if passed_data["approval_type"] == "Pending 1st Pre-Approval":
            sql3 = """
                SELECT user FROM app_user_roles 
                WHERE role = %s AND org_code = %s AND status = %s"""
            data3 = ("team lead", passed_data["org_code"], 1)
            cur.execute(sql3, data3)
            notifyusers = cur.fetchall()

            for notifyuser in notifyusers:
                useremaillogin = notifyuser['user']

                sql4 = """
                    INSERT INTO app_inbox 
                    (title, message, created_datetime, created_by, recipient, source, status, isbroadcast, org_code) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
                data4 = (
                    "1st Pre-Approval",
                    f"{passed_data['txn_type']} {passed_data['txn_reference']} is awaiting your first pre-approval.",
                    now,
                    passed_data["requested_by"],
                    useremaillogin,
                    "wac",
                    "unread",
                    0,
                    passed_data["org_code"]
                )
                cur.execute(sql4, data4)

                subject = f"{passed_data['txn_type']} {passed_data['txn_reference']} - 1st Pre-Approval"
                referencetitle = f"{passed_data['txn_type']} {passed_data['txn_reference']}"

                wac_send_email_notification(useremaillogin, referencetitle, subject, "1st Pre-Approval")
        
        # Notify users for second pre-approval
        if passed_data["approval_type"] == "Pending 2nd Pre-Approval":
            sql3 = """
                SELECT user FROM app_user_roles 
                WHERE role = %s AND org_code = %s AND status = %s"""
            data3 = ("team lead", passed_data["org_code"], 1)
            cur.execute(sql3, data3)
            notifyusers = cur.fetchall()

            for notifyuser in notifyusers:
                useremaillogin = notifyuser['user']

                sql4 = """
                    INSERT INTO app_inbox 
                    (title, message, created_datetime, created_by, recipient, source, status, isbroadcast, org_code) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
                data4 = (
                    "2nd Pre-Approval",
                    f"{passed_data['txn_type']} {passed_data['txn_reference']} is awaiting your second pre-approval.",
                    now,
                    passed_data["requested_by"],
                    useremaillogin,
                    "wac",
                    "unread",
                    0,
                    passed_data["org_code"]
                )
                cur.execute(sql4, data4)

                subject = f"{passed_data['txn_type']} {passed_data['txn_reference']} - 2nd Pre-Approval"
                referencetitle = f"{passed_data['txn_type']} {passed_data['txn_reference']}"
                
                wac_send_email_notification(useremaillogin, referencetitle, subject, "2nd Pre-Approval")
        
        # Notify users for final approval
        if passed_data["approval_type"] == "Pending Approval":
            sql3 = """
                SELECT user FROM app_user_roles 
                WHERE role = %s AND org_code = %s AND status = %s"""
            data3 = ("manager", passed_data["org_code"], 1)
            cur.execute(sql3, data3)
            notifyusers = cur.fetchall()

            for notifyuser in notifyusers:
                useremaillogin = notifyuser['user']

                sql4 = """
                    INSERT INTO app_inbox 
                    (title, message, created_datetime, created_by, recipient, source, status, isbroadcast, org_code) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
                data4 = (
                    "Final Approval",
                    f"{passed_data['txn_type']} {passed_data['txn_reference']} is awaiting your final approval.",
                    now,
                    passed_data["requested_by"],
                    useremaillogin,
                    "wac",
                    "unread",
                    0,
                    passed_data["org_code"]
                )
                cur.execute(sql4, data4)

                subject = f"{passed_data['txn_type']} {passed_data['txn_reference']} - Final Approval"
                referencetitle = f"{passed_data['txn_type']} {passed_data['txn_reference']}"
                
                wac_send_email_notification(useremaillogin, referencetitle, subject, "Final Approval")

        conn.commit()

        # Close the database connection
        cur.close()
        conn.close()

        """
        fcmToken = get_fcm_token_for_user(userId=passed_data["requested_by"], orgCode=passed_data["org_code"])

        logger.info("fcm token: ")
        logger.info(fcm_token)
        
        logger.info("send notif to fcm")

        # notify front-end/web-app to do refresh
        send_fcm_notification(title="New Message", body="You have a new inbox message", target_token=fcmToken)
        """

        pusher_client.trigger('inbox-channel', 'new-message', {'refresh': True})

        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        return jsonify({"message": "Posted successfully", "result": "inserted"}), 201

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": "Internal server error"}), 500


# update material cost change (cost mgt)
@app.route('/updatematerialcost', methods=['PUT'])
def updatematerialcost():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        org_code = passed_data.get('org_code')
        changes = passed_data.get('changes')
        
        now = timezone2()  # Ensure this function returns the current datetime
        
        for key, value in changes.items():
            itemcode = int(key)
            unitcost = Decimal(value);
            sql1 = """UPDATE physical_items SET unit_cost = %s, updated_datetime = %s  WHERE item_code = %s AND org_code = %s"""
            data1 = (unitcost, now, itemcode, org_code)  
        
            cur.execute(sql1, data1)
        
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 200 status code
        return jsonify({"message": "Updated successfully", "result": "updated"}), 200
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500


# update labor cost change (cost mgt)
@app.route('/updatelaborcost', methods=['PUT'])
def updatelaborcost():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        org_code = passed_data.get('org_code')
        changes = passed_data.get('changes')
        
        now = timezone2()  # Ensure this function returns the current datetime
        
        for key, value in changes.items():
            itemcode = int(key)
            unitcost = Decimal(value);
            sql1 = """UPDATE human_items SET unit_cost = %s, updated_datetime = %s  WHERE item_code = %s AND org_code = %s"""
            data1 = (unitcost, now, itemcode, org_code)  
        
            cur.execute(sql1, data1)
        
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 200 status code
        return jsonify({"message": "Updated successfully", "result": "updated"}), 200
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500
        

# update equipment cost change (cost mgt)
@app.route('/updateequipmentcost', methods=['PUT'])
def updateequipmentcost():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        org_code = passed_data.get('org_code')
        changes = passed_data.get('changes')
        
        now = timezone2()  # Ensure this function returns the current datetime
        
        for key, value in changes.items():
            itemcode = int(key)
            unitcost = Decimal(value);
            sql1 = """UPDATE physical_equip_items SET unit_cost = %s, updated_datetime = %s WHERE item_code = %s AND org_code = %s"""
            data1 = (unitcost, now, itemcode, org_code)  
        
            cur.execute(sql1, data1)
        
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 200 status code
        return jsonify({"message": "Updated successfully", "result": "updated"}), 200
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500
        

# update work order actual total cost
@app.route('/updateactualtotalcost', methods=['PUT'])
def updateactualtotalcost():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        wo_number = passed_data.get('wo_number')
        org_code = passed_data.get('org_code')
        revenue = Decimal(passed_data.get('revenue'))
        actual_total_cost = Decimal(passed_data.get('actual_total_cost'))
        gross_profit = Decimal(passed_data.get('gross_profit'))
        
        now = timezone2()  # Ensure this function returns the current datetime
        
        sql1 = """UPDATE work_orders SET revenue = %s, actual_total_cost = %s, gross_profit = %s WHERE wo_number = %s AND org_code = %s"""
        data1 = (revenue, actual_total_cost, gross_profit, wo_number, org_code)  
        
        cur.execute(sql1, data1)
        
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 200 status code
        return jsonify({"message": "Updated successfully", "result": "updated"}), 200
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500


#--- save message to app inbox ----#
@app.route('/postappinbox', methods=['POST'])
def postappinbox():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        now = timezone2()
        
        # SQL for inserting work request data
        sql1 = """INSERT INTO app_inbox (task_gid, message, created_datetime, created_by, source, org_code) VALUES (%s, %s, %s, %s, %s, %s)"""
        data1 = (passed_data["task_gid"], passed_data["message"], now, passed_data["created_by"], passed_data["source"], passed_data["org_code"])
        
        cur.execute(sql1, data1)
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 201 status code
        return jsonify({"message": "Message posted successfully", "result": "posted"}), 201
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500


#--- save work order design ----#
@app.route('/postwodesign', methods=['POST'])
def postwodesign():
    passed_data = request.get_json()

    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()

        now = timezone2()
        
        total_materials_cost = 0.00
        total_materials_cost_low = 0.00
        total_materials_cost_avg = 0.00
        total_labor_cost = 0.00
        total_equipment_cost = 0.00
        
        #--- SAVING COMPATIBLE UNITS ---

        # SQL for checking if a record exists
        
        check_cu = """SELECT COUNT(*) AS count FROM wo_compatible_units 
                    WHERE wo_number = %s AND task_number = %s AND cu_code = %s AND org_code = %s"""
                      
        # SQL for inserting a new record
        
        insert_cu = """INSERT INTO wo_compatible_units (wo_number, task_number, cu_code,            cu_type, quantity, created_datetime, org_code) 
                VALUES (%s, %s, %s, %s, %s, %s, %s)"""
        
        # SQL for updating an existing record
        
        update_cu = """UPDATE wo_compatible_units 
                    SET cu_type = %s, quantity = %s, created_datetime = %s 
                    WHERE wo_number = %s AND task_number = %s AND cu_code = %s AND org_code = %s"""
        

        # Process each selected CU
        for selected_cu in passed_data["selected_cus"]:
            cu_code = selected_cu.get("code")
            cu_type = selected_cu.get("type")
            quantity = selected_cu.get("quantity")
            org_code = selected_cu.get("org_code")

            # Check if the record exists
            cur.execute(check_cu, (passed_data["wo_number"], passed_data["task_number"], cu_code, passed_data["org_code"]))
            result = cur.fetchall()

            if result and "count" in result[0]:
                count = result[0]["count"]
                exists = count > 0
            else:
                exists = False

            if exists:
                # Update the existing record
                cur.execute(update_cu, (
                    cu_type, quantity, now, 
                    passed_data["wo_number"], passed_data["task_number"], cu_code, passed_data["org_code"]
                ))
            else:
                # Insert a new record
                cur.execute(insert_cu, (
                    passed_data["wo_number"], passed_data["task_number"], cu_code, cu_type, quantity, now, passed_data["org_code"]
                ))
        
        logger.info("done insert cu")

        # Create a temporary table for CU codes
        create_temp_table = """CREATE TEMPORARY TABLE temp_cu_codes (cu_code VARCHAR(255) NOT NULL)"""

        # Insert CU codes into the temporary table
        insert_into_temp = """INSERT INTO temp_cu_codes (cu_code) VALUES (%s)"""

        # Delete records not in the selected CU codes
        
        delete_cu = """DELETE FROM wo_compatible_units WHERE wo_number = %s AND task_number = %s AND cu_code NOT IN (SELECT cu_code FROM temp_cu_codes) AND org_code = %s"""
        
        # Execute: Create the temporary table
        cur.execute(create_temp_table)

        # Execute: Insert CU codes into the temporary table
        cu_codes = [cu["code"] for cu in passed_data["selected_cus"]]
        cur.executemany(insert_into_temp, [(code,) for code in cu_codes])
        
        # Execute: Perform the DELETE operation
        cur.execute(delete_cu, (passed_data["wo_number"], passed_data["task_number"], passed_data["org_code"]))


        #--- SAVING CU MATERIALS ---

        # SQL for checking if a record exists
        
        check_material = """SELECT COUNT(*) AS count FROM wo_task_physical_items 
                        WHERE wo_number = %s AND task_number = %s AND cu_code = %s AND item_code = %s AND org_code = %s"""
        
        # SQL for inserting a new record
        
        insert_material = """INSERT INTO wo_task_physical_items (wo_number, task_number, item_code, quantity, uom, unit_cost, unit_cost_low, unit_cost_avg, total_cost, total_cost_low, total_cost_avg, cu_code, created_datetime, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
            
        # SQL for updating an existing record
        
        update_material = """UPDATE wo_task_physical_items  
                             SET quantity = %s, unit_cost = %s, unit_cost_low = %s, unit_cost_avg = %s, total_cost = %s, total_cost_low = %s, total_cost_avg = %s, created_datetime = %s 
                             WHERE wo_number = %s AND task_number = %s AND cu_code = %s AND item_code = %s AND org_code = %s"""
        
        # Process each selected material
        for selected_material in passed_data["selected_materials"]:
            cu_code = selected_material.get("cu_code")
            item_code = selected_material.get("item_code")
            quantity = selected_material.get("quantity")
            unit_cost = float(selected_material.get("unit_cost").replace(",", ""))
            unit_cost_low = float(selected_material.get("unit_cost_low").replace(",", ""))
            unit_cost_avg = float(selected_material.get("unit_cost_avg").replace(",", ""))
            total_cost = float(quantity) * unit_cost
            total_cost_low = float(quantity) * unit_cost_low
            total_cost_avg = float(quantity) * unit_cost_avg
            uom = selected_material.get("uom")
            org_code = selected_material.get("org_code")
            total_materials_cost = total_materials_cost + total_cost
            total_materials_cost_low = total_materials_cost_low + total_cost_low
            total_materials_cost_avg = total_materials_cost_avg + total_cost_avg
            
            # Check if the record exists
            cur.execute(check_material, (passed_data["wo_number"], passed_data["task_number"], cu_code, item_code, passed_data["org_code"]))
            result = cur.fetchall()

            if result and "count" in result[0]:
                count = result[0]["count"]
                exists = count > 0
            else:
                exists = False

            if exists:
                # Update the existing record
                cur.execute(update_material, (
                    quantity, unit_cost, unit_cost_low, unit_cost_avg, total_cost, total_cost_low, total_cost_avg, now, 
                    passed_data["wo_number"], passed_data["task_number"], cu_code, item_code, passed_data["org_code"]
                ))
            else:
                # Insert a new record
                cur.execute(insert_material, (
                    passed_data["wo_number"], passed_data["task_number"], item_code, quantity, uom, unit_cost, unit_cost_low, unit_cost_avg, total_cost, total_cost_low, total_cost_avg, cu_code, now, passed_data["org_code"]
                ))


        # Create a temporary table for cu_code and item_code
        create_temp_table = """CREATE TEMPORARY TABLE temp_matls_codes (cu_code VARCHAR(255) NOT NULL,item_code VARCHAR(255) NOT NULL)"""

        # Insert cu_code and item_code into the temporary table
        insert_into_temp = """INSERT INTO temp_matls_codes (cu_code, item_code) VALUES (%s, %s)"""

        # Delete records not in the selected item codes
        delete_item = """DELETE FROM wo_task_physical_items WHERE wo_number = %s AND task_number = %s AND CONCAT(cu_code, item_code) NOT IN (SELECT CONCAT(cu_code, item_code) FROM temp_matls_codes) AND org_code = %s"""
        
        # Create the temporary table
        cur.execute(create_temp_table)

        # Prepare data for insertion
        item_codes = [
            (material["cu_code"], material["item_code"])
            for material in passed_data["selected_materials"]
        ]

        # Insert data into the temporary table
        cur.executemany(insert_into_temp, item_codes)
        
        # Perform the DELETE operation
        cur.execute(delete_item, (passed_data["wo_number"], passed_data["task_number"], passed_data["org_code"]))
        

        #--- SAVING CU ALTERATIONS ---
        
        insert_alteration = """INSERT INTO wo_cu_alterations (wo_number, cu_code, cu_title, alteration, created_datetime, org_code) VALUES (%s, %s, %s, %s, %s, %s)"""
        
        for cu_alteration in passed_data["cu_alterations"]:
            cu_code = cu_alteration.get("cu_code")
            cu_title = cu_alteration.get("cu_title")
            alteration = cu_alteration.get("alteration")
            
            # Insert a new record
            if alteration.strip() != "":
                cur.execute(insert_alteration, (
                    passed_data["wo_number"], cu_code, cu_title, alteration, now, passed_data["org_code"]
                ))
            
        
        #--- SAVING CUSTOM MATERIALS ---

        # SQL for checking if a record exists
        check_material = """SELECT COUNT(*) AS count FROM wo_task_physical_custom_items 
                        WHERE wo_number = %s AND task_number = %s AND item_code = %s AND org_code = %s"""

        # SQL for inserting a new record
        insert_material = """INSERT INTO wo_task_physical_custom_items (wo_number, task_number, item_code, quantity, uom, unit_cost, unit_cost_low, unit_cost_avg, total_cost, total_cost_low, total_cost_avg, created_datetime, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""

        # SQL for updating an existing record
        update_material = """UPDATE wo_task_physical_custom_items  
                             SET quantity = %s, unit_cost = %s, unit_cost_low = %s, unit_cost_avg = %s, total_cost = %s, total_cost_low = %s, total_cost_avg = %s, created_datetime = %s 
                             WHERE wo_number = %s AND task_number = %s AND item_code = %s AND org_code = %s"""

        # Process each selected material
        for selected_material in passed_data["selected_custom_matls"]:
            item_code = selected_material.get("item_code")
            quantity = selected_material.get("quantity")
            unit_cost = float(selected_material.get("unit_cost").replace(",", ""))
            unit_cost_low = float(selected_material.get("unit_cost_low").replace(",", ""))
            unit_cost_avg = float(selected_material.get("unit_cost_avg").replace(",", ""))
            total_cost = float(quantity) * unit_cost
            total_cost_low = float(quantity) * unit_cost_low
            total_cost_avg = float(quantity) * unit_cost_avg
            uom = selected_material.get("uom")
            org_code = selected_material.get("org_code")
            total_materials_cost = total_materials_cost + total_cost
            total_materials_cost_low = total_materials_cost_low + total_cost_low
            total_materials_cost_avg = total_materials_cost_avg + total_cost_avg
            
            # Check if the record exists
            cur.execute(check_material, (passed_data["wo_number"], passed_data["task_number"], item_code, passed_data["org_code"]))
            result = cur.fetchall()

            if result and "count" in result[0]:
                count = result[0]["count"]
                exists = count > 0
            else:
                exists = False

            if exists:
                # Update the existing record
                cur.execute(update_material, (
                    quantity, unit_cost, unit_cost_low, unit_cost_avg, total_cost, total_cost_low, total_cost_avg, now, 
                    passed_data["wo_number"], passed_data["task_number"], item_code, passed_data["org_code"]
                ))
            else:
                # Insert a new record
                cur.execute(insert_material, (
                    passed_data["wo_number"], passed_data["task_number"], item_code, quantity, uom, unit_cost, unit_cost_low, unit_cost_avg, total_cost, total_cost_low, total_cost_avg, now, passed_data["org_code"]
                ))

        # Create a temporary table for cu_code and item_code
        create_temp_table = """CREATE TEMPORARY TABLE temp_cmatls_codes (item_code VARCHAR(255) NOT NULL)"""

        # Insert cu_code and item_code into the temporary table
        insert_into_temp = """INSERT INTO temp_cmatls_codes (item_code) VALUES (%s)"""

        # Delete records not in the selected item codes
        delete_item = """DELETE FROM wo_task_physical_custom_items WHERE wo_number = %s AND task_number = %s AND item_code NOT IN (SELECT item_code FROM temp_cmatls_codes) AND org_code = %s"""
            
        # Create the temporary table
        cur.execute(create_temp_table)

        # Prepare data for insertion
        item_codes = [
            (material["item_code"])
            for material in passed_data["selected_custom_matls"]
        ]

        # Insert data into the temporary table
        cur.executemany(insert_into_temp, item_codes)
        
        # Perform the DELETE operation
        cur.execute(delete_item, (passed_data["wo_number"], passed_data["task_number"], passed_data["org_code"]))
        
        #--- SAVING COST ESTIMATE ----
        
        # SQL for checking if a record exists
        check_cost = """SELECT COUNT(*) AS count FROM wo_cost_estimates 
                      WHERE wo_number = %s AND org_code = %s"""

        # SQL for inserting a new record
        insert_cost = """INSERT INTO wo_cost_estimates (
                        wo_number, 
                        materials_cost, 
                        materials_cost_low, 
                        materials_cost_avg, 
                        total_cost, 
                        total_cost_low, 
                        total_cost_avg, 
                        created_datetime, 
                        org_code
                        ) VALUES (
                            %s, 
                            %s,
                            %s,
                            %s,
                            (
                            COALESCE(materials_cost, 0) + 
                            COALESCE(labor_cost, 0) + 
                            COALESCE(equipment_cost, 0) + 
                            COALESCE(overhead_cost, 0) + 
                            COALESCE(contingency_fund, 0)
                            ) - COALESCE(discounts, 0), 
                            (
                            COALESCE(materials_cost_low, 0) + 
                            COALESCE(labor_cost, 0) + 
                            COALESCE(equipment_cost, 0) + 
                            COALESCE(overhead_cost, 0) + 
                            COALESCE(contingency_fund, 0)
                            ) - COALESCE(discounts, 0), 
                            (
                            COALESCE(materials_cost_avg, 0) + 
                            COALESCE(labor_cost, 0) + 
                            COALESCE(equipment_cost, 0) + 
                            COALESCE(overhead_cost, 0) + 
                            COALESCE(contingency_fund, 0)
                            ) - COALESCE(discounts, 0), 
                            %s, 
                            %s
                        )"""
            
        # SQL for updating an existing record
        update_cost = """UPDATE wo_cost_estimates  
                        SET 
                        materials_cost = %s, 
                        materials_cost_low = %s, 
                        materials_cost_avg = %s, 
                        total_cost = (
                            COALESCE(materials_cost, 0) + 
                            COALESCE(labor_cost, 0) + 
                            COALESCE(equipment_cost, 0) + 
                            COALESCE(overhead_cost, 0) + 
                            COALESCE(contingency_fund, 0)
                            ) - COALESCE(discounts, 0), 
                        total_cost_low = (
                            COALESCE(materials_cost_low, 0) + 
                            COALESCE(labor_cost, 0) + 
                            COALESCE(equipment_cost, 0) + 
                            COALESCE(overhead_cost, 0) + 
                            COALESCE(contingency_fund, 0)
                            ) - COALESCE(discounts, 0), 
                        total_cost_avg = (
                            COALESCE(materials_cost_avg, 0) + 
                            COALESCE(labor_cost, 0) + 
                            COALESCE(equipment_cost, 0) + 
                            COALESCE(overhead_cost, 0) + 
                            COALESCE(contingency_fund, 0)
                            ) - COALESCE(discounts, 0), 
                        created_datetime = %s 
                        WHERE 
                            wo_number = %s 
                            AND org_code = %s"""

        # Check if the record exists
        cur.execute(check_cost, (passed_data["wo_number"], passed_data["org_code"]))
        result = cur.fetchall()
        

        if result and "count" in result[0]:
            count = result[0]["count"]
            exists = count > 0
        else:
            exists = False

        if exists:
            # Update the existing record
            cur.execute(update_cost, (
                total_materials_cost, total_materials_cost_low, total_materials_cost_avg, now, passed_data["wo_number"], passed_data["org_code"]))
        else:
            # Insert a new record
            cur.execute(insert_cost, (
                passed_data["wo_number"], total_materials_cost, total_materials_cost_low, total_materials_cost_avg, now, passed_data["org_code"]))
        
        #--- SAVING HUMAN COMPATIBLE UNITS ---

        # SQL for checking if a record exists
        check_cu = """SELECT COUNT(*) AS count FROM wo_human_compatible_units 
                      WHERE wo_number = %s AND task_number = %s AND cu_code = %s AND org_code = %s"""

        # SQL for inserting a new record
        insert_cu = """INSERT INTO wo_human_compatible_units (wo_number, task_number, cu_code, cu_type, quantity, created_datetime, org_code) 
                       VALUES (%s, %s, %s, %s, %s, %s, %s)"""
                       
        # SQL for updating an existing record
        update_cu = """UPDATE wo_human_compatible_units 
                    SET cu_type = %s, quantity = %s, created_datetime = %s 
                    WHERE wo_number = %s AND task_number = %s AND cu_code = %s AND org_code = %s"""
        
        # Process each selected CU
        for selected_cu in passed_data["selected_human_cus"]:
            cu_code = selected_cu.get("code")
            cu_type = selected_cu.get("type")
            quantity = selected_cu.get("quantity")
            org_code = selected_cu.get("org_code")

            # Check if the record exists
            cur.execute(check_cu, (passed_data["wo_number"], passed_data["task_number"], cu_code, passed_data["org_code"]))
            result = cur.fetchall()

            if result and "count" in result[0]:
                count = result[0]["count"]
                exists = count > 0
            else:
                exists = False

            if exists:
                # Update the existing record
                cur.execute(update_cu, (
                    cu_type, quantity, now, 
                    passed_data["wo_number"], passed_data["task_number"], cu_code, passed_data["org_code"]
                ))
            else:
                # Insert a new record
                cur.execute(insert_cu, (
                    passed_data["wo_number"], passed_data["task_number"], cu_code, cu_type, quantity, now, passed_data["org_code"]
                ))
                
        # Create a temporary table for CU codes
        create_temp_table = """CREATE TEMPORARY TABLE temp_hcu_codes (cu_code VARCHAR(255) NOT NULL)"""

        # Insert CU codes into the temporary table
        insert_into_temp = """INSERT INTO temp_hcu_codes (cu_code) VALUES (%s)"""

        # Delete records not in the selected CU codes
        delete_cu = """DELETE FROM wo_human_compatible_units WHERE wo_number = %s AND task_number = %s AND cu_code NOT IN (SELECT cu_code FROM temp_hcu_codes) AND org_code = %s"""
        
        # Execute: Create the temporary table
        cur.execute(create_temp_table)

        # Execute: Insert CU codes into the temporary table
        cu_codes = [cu["code"] for cu in passed_data["selected_human_cus"]]
        cur.executemany(insert_into_temp, [(code,) for code in cu_codes])
        
        # Execute: Perform the DELETE operation
        cur.execute(delete_cu, (passed_data["wo_number"], passed_data["task_number"], passed_data["org_code"]))

        
        #--- SAVING HUMAN CU LABOR ITEMS ---

        # SQL for checking if a record exists
        check_material = """SELECT COUNT(*) AS count FROM wo_task_human_items 
                            WHERE wo_number = %s AND task_number = %s AND cu_code = %s AND item_code = %s AND org_code = %s"""
                            
        # SQL for inserting a new record
        insert_material = """INSERT INTO wo_task_human_items (wo_number, task_number, item_code, quantity, uom, unit_cost, total_cost, cu_code, created_datetime, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""

        # SQL for updating an existing record
        update_material = """UPDATE wo_task_human_items  
                             SET quantity = %s, unit_cost = %s, total_cost = %s, created_datetime = %s 
                             WHERE wo_number = %s AND task_number = %s AND cu_code = %s AND item_code = %s AND org_code = %s"""
        
        # Process each selected labor items
        for selected_material in passed_data["selected_labors"]:
            cu_code = selected_material.get("cu_code")
            item_code = selected_material.get("item_code")
            quantity = selected_material.get("quantity")
            unit_cost = float(selected_material.get("unit_cost").replace(",", ""))
            total_cost = float(quantity) * unit_cost
            uom = selected_material.get("uom")
            org_code = selected_material.get("org_code")
            total_labor_cost = total_labor_cost + total_cost
            
            # Check if the record exists
            cur.execute(check_material, (passed_data["wo_number"], passed_data["task_number"], cu_code, item_code, passed_data["org_code"]))
            result = cur.fetchall()

            if result and "count" in result[0]:
                count = result[0]["count"]
                exists = count > 0
            else:
                exists = False

            if exists:
                # Update the existing record
                cur.execute(update_material, (
                    quantity, unit_cost, total_cost, now, 
                    passed_data["wo_number"], passed_data["task_number"], cu_code, item_code, passed_data["org_code"]
                ))
            else:
                # Insert a new record
                cur.execute(insert_material, (
                    passed_data["wo_number"], passed_data["task_number"], item_code, quantity, uom, unit_cost, total_cost, cu_code, now, passed_data["org_code"]
                ))

        # Create a temporary table for cu_code and item_code
        create_temp_table = """CREATE TEMPORARY TABLE temp_labors_codes (cu_code VARCHAR(255) NOT NULL,item_code VARCHAR(255) NOT NULL)"""

        # Insert cu_code and item_code into the temporary table
        insert_into_temp = """INSERT INTO temp_labors_codes (cu_code, item_code) VALUES (%s, %s)"""

        # Delete records not in the selected item codes
        delete_item = """DELETE FROM wo_task_human_items WHERE wo_number = %s AND task_number = %s AND CONCAT(cu_code, item_code) NOT IN (SELECT CONCAT(cu_code, item_code) FROM temp_labors_codes) AND org_code = %s"""
            
        # Create the temporary table
        cur.execute(create_temp_table)

        # Prepare data for insertion
        item_codes = [
            (material["cu_code"], material["item_code"])
            for material in passed_data["selected_labors"]
        ]

        # Insert data into the temporary table
        cur.executemany(insert_into_temp, item_codes)
        
        # Perform the DELETE operation
        cur.execute(delete_item, (passed_data["wo_number"], passed_data["task_number"], passed_data["org_code"]))
        
        #--- SAVING CU LABOR ALTERATIONS ---
        
        insert_alteration_labor = """INSERT INTO wo_cu_alterations (wo_number, cu_code, cu_title, alteration, created_datetime, org_code) VALUES (%s, %s, %s, %s, %s, %s)"""
        
        for cu_alteration_labor in passed_data["cu_alterations_labor"]:
            cu_code_labor = cu_alteration_labor.get("cu_code")
            cu_title_labor = cu_alteration_labor.get("cu_title")
            alteration_labor = cu_alteration_labor.get("alteration")
            
            # Insert a new record
            if alteration_labor.strip() != "":
                cur.execute(insert_alteration_labor, (
                        passed_data["wo_number"], cu_code_labor, cu_title_labor, alteration_labor, now, passed_data["org_code"]
                ))
        
        #--- SAVING CUSTOM LABOR ITEMS ---

        # SQL for checking if a record exists
        check_material = """SELECT COUNT(*) AS count FROM wo_task_human_custom_items 
                            WHERE wo_number = %s AND task_number = %s AND item_code = %s AND org_code = %s"""
                            
        # SQL for inserting a new record
        insert_material = """INSERT INTO wo_task_human_custom_items (wo_number, task_number, item_code, quantity, uom, unit_cost, total_cost, created_datetime, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
            
        # SQL for updating an existing record
        update_material = """UPDATE wo_task_human_custom_items  
                             SET quantity = %s, unit_cost = %s, total_cost = %s, created_datetime = %s 
                             WHERE wo_number = %s AND task_number = %s AND item_code = %s AND org_code = %s"""

        # Process each selected labor items
        for selected_material in passed_data["selected_custom_labors"]:
            item_code = selected_material.get("item_code")
            quantity = selected_material.get("quantity")
            unit_cost = float(selected_material.get("unit_cost").replace(",", ""))
            total_cost = float(quantity) * unit_cost
            uom = selected_material.get("uom")
            org_code = selected_material.get("org_code")
            total_labor_cost = total_labor_cost + total_cost
            
            # Check if the record exists
            cur.execute(check_material, (passed_data["wo_number"], passed_data["task_number"], item_code, passed_data["org_code"]))
            result = cur.fetchall()

            if result and "count" in result[0]:
                count = result[0]["count"]
                exists = count > 0
            else:
                exists = False

            if exists:
                # Update the existing record
                cur.execute(update_material, (
                    quantity, unit_cost, total_cost, now, 
                    passed_data["wo_number"], passed_data["task_number"], item_code, passed_data["org_code"]
                ))
            else:
                # Insert a new record
                cur.execute(insert_material, (
                    passed_data["wo_number"], passed_data["task_number"], item_code, quantity, uom, unit_cost, total_cost, now, passed_data["org_code"]
                ))

        # Create a temporary table for cu_code and item_code
        create_temp_table = """CREATE TEMPORARY TABLE temp_hcmatls_codes (item_code VARCHAR(255) NOT NULL)"""

        # Insert cu_code and item_code into the temporary table
        insert_into_temp = """INSERT INTO temp_hcmatls_codes (item_code) VALUES (%s)"""

        # Delete records not in the selected item codes
        delete_item = """DELETE FROM wo_task_human_custom_items WHERE wo_number = %s AND task_number = %s AND item_code NOT IN (SELECT item_code FROM temp_hcmatls_codes) AND org_code = %s"""
        
        # Create the temporary table
        cur.execute(create_temp_table)

        # Prepare data for insertion
        item_codes = [
            (material["item_code"])
            for material in passed_data["selected_custom_labors"]
        ]

        # Insert data into the temporary table
        cur.executemany(insert_into_temp, item_codes)
        
        # Perform the DELETE operation
        cur.execute(delete_item, (passed_data["wo_number"], passed_data["task_number"], passed_data["org_code"]))
        
        
        #--- SAVING LABOR COST ESTIMATE ----
        
        # SQL for checking if a record exists
        check_cost = """SELECT COUNT(*) AS count FROM wo_cost_estimates 
                      WHERE wo_number = %s AND org_code = %s"""
                      
        # SQL for inserting a new record
        insert_cost = """INSERT INTO wo_cost_estimates (
                        wo_number, 
                        labor_cost, 
                        total_cost, 
                        created_datetime, 
                        org_code
                        ) VALUES (
                            %s, 
                            %s, 
                            (
                            COALESCE(materials_cost, 0) + 
                            COALESCE(labor_cost, 0) + 
                            COALESCE(equipment_cost, 0) + 
                            COALESCE(overhead_cost, 0) + 
                            COALESCE(contingency_fund, 0)
                            ) - COALESCE(discounts, 0), 
                            %s, 
                            %s
                        )"""

        # SQL for updating an existing record
        update_cost = """UPDATE wo_cost_estimates  
                        SET 
                        labor_cost = %s, 
                        total_cost = (
                            COALESCE(materials_cost, 0) + 
                            COALESCE(labor_cost, 0) + 
                            COALESCE(equipment_cost, 0) + 
                            COALESCE(overhead_cost, 0) + 
                            COALESCE(contingency_fund, 0)
                            ) - COALESCE(discounts, 0), 
                        created_datetime = %s 
                        WHERE 
                            wo_number = %s 
                            AND org_code = %s"""

        # Check if the record exists
        cur.execute(check_cost, (passed_data["wo_number"], passed_data["org_code"]))
        result = cur.fetchall()
        

        if result and "count" in result[0]:
            count = result[0]["count"]
            exists = count > 0
        else:
            exists = False

        if exists:
            # Update the existing record
            cur.execute(update_cost, (
                total_labor_cost, now, passed_data["wo_number"], passed_data["org_code"]))
        else:
            # Insert a new record
            cur.execute(insert_cost, (
                passed_data["wo_number"], total_labor_cost, now, passed_data["org_code"]))
        
        
        #--- SAVING EQUIPMENT COMPATIBLE UNITS ---

        # SQL for checking if a record exists
        check_cu = """SELECT COUNT(*) AS count FROM wo_equip_compatible_units 
                      WHERE wo_number = %s AND task_number = %s AND cu_code = %s AND org_code = %s"""
                      
        # SQL for inserting a new record
        insert_cu = """INSERT INTO wo_equip_compatible_units (wo_number, task_number, cu_code, cu_type, quantity, created_datetime, org_code) 
                       VALUES (%s, %s, %s, %s, %s, %s, %s)"""
                       
        # SQL for updating an existing record
        update_cu = """UPDATE wo_equip_compatible_units 
                       SET cu_type = %s, quantity = %s, created_datetime = %s 
                       WHERE wo_number = %s AND task_number = %s AND cu_code = %s AND org_code = %s"""
        
        # Process each selected CU
        for selected_cu in passed_data["selected_equip_cus"]:
            cu_code = selected_cu.get("code")
            cu_type = selected_cu.get("type")
            quantity = selected_cu.get("quantity")
            org_code = selected_cu.get("org_code")

            # Check if the record exists
            cur.execute(check_cu, (passed_data["wo_number"], passed_data["task_number"], cu_code, passed_data["org_code"]))
            result = cur.fetchall()

            if result and "count" in result[0]:
                count = result[0]["count"]
                exists = count > 0
            else:
                exists = False

            if exists:
                # Update the existing record
                cur.execute(update_cu, (
                    cu_type, quantity, now, 
                    passed_data["wo_number"], passed_data["task_number"], cu_code, passed_data["org_code"]
                ))
            else:
                # Insert a new record
                cur.execute(insert_cu, (
                    passed_data["wo_number"], passed_data["task_number"], cu_code, cu_type, quantity, now, passed_data["org_code"]
                ))
        
        # Create a temporary table for CU codes
        create_temp_table = """CREATE TEMPORARY TABLE temp_ecu_codes (cu_code VARCHAR(255) NOT NULL)"""

        # Insert CU codes into the temporary table
        insert_into_temp = """INSERT INTO temp_ecu_codes (cu_code) VALUES (%s)"""

        # Delete records not in the selected CU codes
        delete_cu = """DELETE FROM wo_equip_compatible_units WHERE wo_number = %s AND task_number = %s AND cu_code NOT IN (SELECT cu_code FROM temp_ecu_codes) AND org_code = %s"""
        
        # Execute: Create the temporary table
        cur.execute(create_temp_table)

        # Execute: Insert CU codes into the temporary table
        cu_codes = [cu["code"] for cu in passed_data["selected_equip_cus"]]
        cur.executemany(insert_into_temp, [(code,) for code in cu_codes])
        
        # Execute: Perform the DELETE operation
        cur.execute(delete_cu, (passed_data["wo_number"], passed_data["task_number"], passed_data["org_code"]))

        
        #--- SAVING EQUIPMENT CU MATERIALS ---

        # SQL for checking if a record exists
        check_material = """SELECT COUNT(*) AS count FROM wo_task_physical_equip_items 
                            WHERE wo_number = %s AND task_number = %s AND cu_code = %s AND item_code = %s AND org_code = %s"""
                            
        # SQL for inserting a new record
        insert_material = """INSERT INTO wo_task_physical_equip_items (wo_number, task_number, item_code, quantity, uom, unit_cost, total_cost, cu_code, created_datetime, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
        
        # SQL for updating an existing record
        update_material = """UPDATE wo_task_physical_equip_items   
                             SET quantity = %s, unit_cost = %s, total_cost = %s, created_datetime = %s 
                             WHERE wo_number = %s AND task_number = %s AND cu_code = %s AND item_code = %s AND org_code = %s"""
                             
        # Process each selected material
        for selected_material in passed_data["selected_equipment"]:
            cu_code = selected_material.get("cu_code")
            item_code = selected_material.get("item_code")
            quantity = selected_material.get("quantity")
            unit_cost = float(selected_material.get("unit_cost").replace(",", ""))
            total_cost = float(quantity) * unit_cost
            uom = selected_material.get("uom")
            org_code = selected_material.get("org_code")
            total_equipment_cost = total_equipment_cost + total_cost
            
            # Check if the record exists
            cur.execute(check_material, (passed_data["wo_number"], passed_data["task_number"], cu_code, item_code, passed_data["org_code"]))
            result = cur.fetchall()

            if result and "count" in result[0]:
                count = result[0]["count"]
                exists = count > 0
            else:
                exists = False

            if exists:
                # Update the existing record
                cur.execute(update_material, (
                    quantity, unit_cost, total_cost, now, 
                    passed_data["wo_number"], passed_data["task_number"], cu_code, item_code, passed_data["org_code"]
                ))
            else:
                # Insert a new record
                cur.execute(insert_material, (
                    passed_data["wo_number"], passed_data["task_number"], item_code, quantity, uom, unit_cost, total_cost, cu_code, now, passed_data["org_code"]
                ))

        # Create a temporary table for cu_code and item_code
        create_temp_table = """CREATE TEMPORARY TABLE temp_ematls_codes (cu_code VARCHAR(255) NOT NULL,item_code VARCHAR(255) NOT NULL)"""

        # Insert cu_code and item_code into the temporary table
        insert_into_temp = """INSERT INTO temp_ematls_codes (cu_code, item_code) VALUES (%s, %s)"""

        # Delete records not in the selected item codes
        delete_item = """DELETE FROM wo_task_physical_equip_items WHERE wo_number = %s AND task_number = %s AND CONCAT(cu_code, item_code) NOT IN (SELECT CONCAT(cu_code, item_code) FROM temp_ematls_codes) AND org_code = %s"""
            
        # Create the temporary table
        cur.execute(create_temp_table)

        # Prepare data for insertion
        item_codes = [
            (material["cu_code"], material["item_code"])
            for material in passed_data["selected_equipment"]
        ]

        # Insert data into the temporary table
        cur.executemany(insert_into_temp, item_codes)
        
        # Perform the DELETE operation
        cur.execute(delete_item, (passed_data["wo_number"], passed_data["task_number"], passed_data["org_code"]))
        
        #--- SAVING CU EQUIPMENT ALTERATIONS ---
        
        insert_alteration_equipment = """INSERT INTO wo_cu_alterations (wo_number, cu_code, cu_title, alteration, created_datetime, org_code) VALUES (%s, %s, %s, %s, %s, %s)"""
        
        for cu_alteration_equipment in passed_data["cu_alterations_equipment"]:
            cu_code_equipment = cu_alteration_equipment.get("cu_code")
            cu_title_equipment = cu_alteration_equipment.get("cu_title")
            alteration_equipment = cu_alteration_equipment.get("alteration")
            
            # Insert a new record
            if alteration_equipment.strip() != "":
                cur.execute(insert_alteration_equipment, (
                        passed_data["wo_number"], cu_code_equipment, cu_title_equipment, alteration_equipment, now, passed_data["org_code"]
                ))
        
        
        #--- SAVING EQUIPMENT CUSTOM MATERIALS ---

        # SQL for checking if a record exists
        
        check_material = """SELECT COUNT(*) AS count FROM wo_task_physical_equip_custom_items 
                            WHERE wo_number = %s AND task_number = %s AND item_code = %s AND org_code = %s"""
                            
        # SQL for inserting a new record
        insert_material = """INSERT INTO wo_task_physical_equip_custom_items (wo_number, task_number, item_code, quantity, uom, unit_cost, total_cost, created_datetime, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
            
        # SQL for updating an existing record
        update_material = """UPDATE wo_task_physical_equip_custom_items  
                             SET quantity = %s, unit_cost = %s, total_cost = %s, created_datetime = %s 
                             WHERE wo_number = %s AND task_number = %s AND item_code = %s AND org_code = %s"""
                             
        # Process each selected material
        for selected_material in passed_data["selected_custom_equipment"]:
            item_code = selected_material.get("item_code")
            quantity = selected_material.get("quantity")
            unit_cost = float(selected_material.get("unit_cost").replace(",", ""))
            total_cost = float(quantity) * unit_cost
            uom = selected_material.get("uom")
            org_code = selected_material.get("org_code")
            total_equipment_cost = total_equipment_cost + total_cost
            
            # Check if the record exists
            cur.execute(check_material, (passed_data["wo_number"], passed_data["task_number"], item_code, passed_data["org_code"]))
            result = cur.fetchall()

            if result and "count" in result[0]:
                count = result[0]["count"]
                exists = count > 0
            else:
                exists = False

            if exists:
                # Update the existing record
                cur.execute(update_material, (
                    quantity, unit_cost, total_cost, now, 
                    passed_data["wo_number"], passed_data["task_number"], item_code, passed_data["org_code"]
                ))
            else:
                # Insert a new record
                cur.execute(insert_material, (
                    passed_data["wo_number"], passed_data["task_number"], item_code, quantity, uom, unit_cost, total_cost, now, passed_data["org_code"]
                ))

        # Create a temporary table for cu_code and item_code
        create_temp_table = """CREATE TEMPORARY TABLE temp_ecmatls_codes (item_code VARCHAR(255) NOT NULL)"""

        # Insert cu_code and item_code into the temporary table
        insert_into_temp = """INSERT INTO temp_ecmatls_codes (item_code) VALUES (%s)"""

        # Delete records not in the selected item codes
        delete_item = """DELETE FROM wo_task_physical_equip_custom_items WHERE wo_number = %s AND task_number = %s AND item_code NOT IN (SELECT item_code FROM temp_ecmatls_codes) AND org_code = %s"""
            
        # Create the temporary table
        cur.execute(create_temp_table)

        # Prepare data for insertion
        item_codes = [
            (material["item_code"])
            for material in passed_data["selected_custom_equipment"]
        ]

        # Insert data into the temporary table
        cur.executemany(insert_into_temp, item_codes)
        
        # Perform the DELETE operation
        cur.execute(delete_item, (passed_data["wo_number"], passed_data["task_number"], passed_data["org_code"]))
        

        #--- SAVING EQUIPMENT COST ESTIMATE ----
        
        # SQL for checking if a record exists
        check_cost = """SELECT COUNT(*) AS count FROM wo_cost_estimates 
                      WHERE wo_number = %s AND org_code = %s"""
                      
        # SQL for inserting a new record
        insert_cost = """INSERT INTO wo_cost_estimates (
                        wo_number, 
                        equipment_cost, 
                        total_cost, 
                        created_datetime, 
                        org_code
                        ) VALUES (
                            %s, 
                            %s, 
                            (
                            COALESCE(materials_cost, 0) + 
                            COALESCE(labor_cost, 0) + 
                            COALESCE(equipment_cost, 0) + 
                            COALESCE(overhead_cost, 0) + 
                            COALESCE(contingency_fund, 0)
                            ) - COALESCE(discounts, 0), 
                            %s, 
                            %s
                        )"""
                        
        # SQL for updating an existing record
        update_cost = """UPDATE wo_cost_estimates  
                        SET 
                        equipment_cost = %s, 
                        total_cost = (
                            COALESCE(materials_cost, 0) + 
                            COALESCE(labor_cost, 0) + 
                            COALESCE(equipment_cost, 0) + 
                            COALESCE(overhead_cost, 0) + 
                            COALESCE(contingency_fund, 0)
                            ) - COALESCE(discounts, 0), 
                        created_datetime = %s 
                        WHERE 
                            wo_number = %s 
                            AND org_code = %s"""
                            
        # Check if the record exists
        cur.execute(check_cost, (passed_data["wo_number"], passed_data["org_code"]))
        result = cur.fetchall()
        

        if result and "count" in result[0]:
            count = result[0]["count"]
            exists = count > 0
        else:
            exists = False

        if exists:
            # Update the existing record
            cur.execute(update_cost, (
                total_equipment_cost, now, passed_data["wo_number"], passed_data["org_code"]))
        else:
            # Insert a new record
            cur.execute(insert_cost, (
                passed_data["wo_number"], total_equipment_cost, now, passed_data["org_code"]))
        
        conn.commit()

        # Close the database connection
        cur.close()
        conn.close()

        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True

        # Return success response with 201 status code
        return jsonify({"message": "Operation completed successfully", "result": "posted"}), 201

    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error", "details": str(e)}), 500


#--- save work order design for standalone ----#
@app.route('/postwodesign2', methods=['POST'])
def postwodesign2():
    passed_data = request.get_json()

    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()

        now = timezone2()
        
        total_materials_cost = 0.00
        total_labor_cost = 0.00
        total_equipment_cost = 0.00
        
        #--- SAVING COMPATIBLE UNITS ---

        # SQL for checking if a record exists
        
        check_cu = """SELECT COUNT(*) AS count FROM sa_compatible_units 
                    WHERE wo_number = %s AND task_number = %s AND cu_code = %s AND org_code = %s"""
                      
        # SQL for inserting a new record
        
        insert_cu = """INSERT INTO sa_compatible_units (wo_number, task_number, cu_code,            cu_type, quantity, created_datetime, org_code) 
                VALUES (%s, %s, %s, %s, %s, %s, %s)"""
        
        # SQL for updating an existing record
        
        update_cu = """UPDATE sa_compatible_units 
                    SET cu_type = %s, quantity = %s, created_datetime = %s 
                    WHERE wo_number = %s AND task_number = %s AND cu_code = %s AND org_code = %s"""
        
        # Process each selected CU
        for selected_cu in passed_data["selected_cus"]:
            cu_code = selected_cu.get("code")
            cu_type = selected_cu.get("type")
            quantity = selected_cu.get("quantity")
            org_code = selected_cu.get("org_code")

            # Check if the record exists
            cur.execute(check_cu, (passed_data["wo_number"], passed_data["task_number"], cu_code, passed_data["org_code"]))
            result = cur.fetchall()

            if result and "count" in result[0]:
                count = result[0]["count"]
                exists = count > 0
            else:
                exists = False

            if exists:
                # Update the existing record
                cur.execute(update_cu, (
                    cu_type, quantity, now, 
                    passed_data["wo_number"], passed_data["task_number"], cu_code, passed_data["org_code"]
                ))
            else:
                # Insert a new record
                cur.execute(insert_cu, (
                    passed_data["wo_number"], passed_data["task_number"], cu_code, cu_type, quantity, now, passed_data["org_code"]
                ))
        
        # Create a temporary table for CU codes
        create_temp_table = """CREATE TEMPORARY TABLE temp_cu_codes (cu_code VARCHAR(255) NOT NULL)"""

        # Insert CU codes into the temporary table
        insert_into_temp = """INSERT INTO temp_cu_codes (cu_code) VALUES (%s)"""

        # Delete records not in the selected CU codes
        
        delete_cu = """DELETE FROM sa_compatible_units WHERE wo_number = %s AND task_number = %s AND cu_code NOT IN (SELECT cu_code FROM temp_cu_codes) AND org_code = %s"""
        
        # Execute: Create the temporary table
        cur.execute(create_temp_table)

        # Execute: Insert CU codes into the temporary table
        cu_codes = [cu["code"] for cu in passed_data["selected_cus"]]
        cur.executemany(insert_into_temp, [(code,) for code in cu_codes])
        
        # Execute: Perform the DELETE operation
        cur.execute(delete_cu, (passed_data["wo_number"], passed_data["task_number"], passed_data["org_code"]))

        
        #--- SAVING CU MATERIALS ---

        # SQL for checking if a record exists
        
        check_material = """SELECT COUNT(*) AS count FROM sa_task_physical_items 
                        WHERE wo_number = %s AND task_number = %s AND cu_code = %s AND item_code = %s AND org_code = %s"""
        
        # SQL for inserting a new record
        
        insert_material = """INSERT INTO sa_task_physical_items (wo_number, task_number, item_code, quantity, uom, unit_cost, total_cost, cu_code, created_datetime, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
            
        # SQL for updating an existing record
        
        update_material = """UPDATE sa_task_physical_items  
                             SET quantity = %s, unit_cost = %s, total_cost = %s, created_datetime = %s 
                             WHERE wo_number = %s AND task_number = %s AND cu_code = %s AND item_code = %s AND org_code = %s"""

        # Process each selected material
        for selected_material in passed_data["selected_materials"]:
            cu_code = selected_material.get("cu_code")
            item_code = selected_material.get("item_code")
            quantity = selected_material.get("quantity")
            unit_cost = float(selected_material.get("unit_cost").replace(",", ""))
            total_cost = float(quantity) * unit_cost
            uom = selected_material.get("uom")
            org_code = selected_material.get("org_code")
            total_materials_cost = total_materials_cost + total_cost
            
            # Check if the record exists
            cur.execute(check_material, (passed_data["wo_number"], passed_data["task_number"], cu_code, item_code, passed_data["org_code"]))
            result = cur.fetchall()

            if result and "count" in result[0]:
                count = result[0]["count"]
                exists = count > 0
            else:
                exists = False

            if exists:
                # Update the existing record
                cur.execute(update_material, (
                    quantity, unit_cost, total_cost, now, 
                    passed_data["wo_number"], passed_data["task_number"], cu_code, item_code, passed_data["org_code"]
                ))
            else:
                # Insert a new record
                cur.execute(insert_material, (
                    passed_data["wo_number"], passed_data["task_number"], item_code, quantity, uom, unit_cost, total_cost, cu_code, now, passed_data["org_code"]
                ))

        # Create a temporary table for cu_code and item_code
        create_temp_table = """CREATE TEMPORARY TABLE temp_matls_codes (cu_code VARCHAR(255) NOT NULL,item_code VARCHAR(255) NOT NULL)"""

        # Insert cu_code and item_code into the temporary table
        insert_into_temp = """INSERT INTO temp_matls_codes (cu_code, item_code) VALUES (%s, %s)"""

        # Delete records not in the selected item codes
        delete_item = """DELETE FROM sa_task_physical_items WHERE wo_number = %s AND task_number = %s AND CONCAT(cu_code, item_code) NOT IN (SELECT CONCAT(cu_code, item_code) FROM temp_matls_codes) AND org_code = %s"""
        
        # Create the temporary table
        cur.execute(create_temp_table)

        # Prepare data for insertion
        item_codes = [
            (material["cu_code"], material["item_code"])
            for material in passed_data["selected_materials"]
        ]

        # Insert data into the temporary table
        cur.executemany(insert_into_temp, item_codes)
        
        # Perform the DELETE operation
        cur.execute(delete_item, (passed_data["wo_number"], passed_data["task_number"], passed_data["org_code"]))
        
        
        #--- SAVING CU ALTERATIONS ---
        
        insert_alteration = """INSERT INTO sa_cu_alterations (wo_number, cu_code, alteration, created_datetime, org_code) VALUES (%s, %s, %s, %s, %s)"""
        
        for cu_alteration in passed_data["cu_alterations"]:
            cu_code = cu_alteration.get("cu_code")
            alteration = cu_alteration.get("alteration")
            
            # Insert a new record
            if alteration.strip() != "":
                cur.execute(insert_alteration, (
                    passed_data["wo_number"], cu_code, alteration, now, passed_data["org_code"]
                ))
        
        
        #--- SAVING CUSTOM MATERIALS ---

        # SQL for checking if a record exists
        check_material = """SELECT COUNT(*) AS count FROM sa_task_physical_custom_items 
                        WHERE wo_number = %s AND task_number = %s AND item_code = %s AND org_code = %s"""

        # SQL for inserting a new record
        insert_material = """INSERT INTO sa_task_physical_custom_items (wo_number, task_number, item_code, quantity, uom, unit_cost, total_cost, created_datetime, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""

        # SQL for updating an existing record
        update_material = """UPDATE sa_task_physical_custom_items  
                             SET quantity = %s, unit_cost = %s, total_cost = %s, created_datetime = %s 
                             WHERE wo_number = %s AND task_number = %s AND item_code = %s AND org_code = %s"""

        # Process each selected material
        for selected_material in passed_data["selected_custom_matls"]:
            item_code = selected_material.get("item_code")
            quantity = selected_material.get("quantity")
            unit_cost = float(selected_material.get("unit_cost").replace(",", ""))
            total_cost = float(quantity) * unit_cost
            uom = selected_material.get("uom")
            org_code = selected_material.get("org_code")
            total_materials_cost = total_materials_cost + total_cost
            
            # Check if the record exists
            cur.execute(check_material, (passed_data["wo_number"], passed_data["task_number"], item_code, passed_data["org_code"]))
            result = cur.fetchall()

            if result and "count" in result[0]:
                count = result[0]["count"]
                exists = count > 0
            else:
                exists = False

            if exists:
                # Update the existing record
                cur.execute(update_material, (
                    quantity, unit_cost, total_cost, now, 
                    passed_data["wo_number"], passed_data["task_number"], item_code, passed_data["org_code"]
                ))
            else:
                # Insert a new record
                cur.execute(insert_material, (
                    passed_data["wo_number"], passed_data["task_number"], item_code, quantity, uom, unit_cost, total_cost, now, passed_data["org_code"]
                ))

        # Create a temporary table for cu_code and item_code
        create_temp_table = """CREATE TEMPORARY TABLE temp_cmatls_codes (item_code VARCHAR(255) NOT NULL)"""

        # Insert cu_code and item_code into the temporary table
        insert_into_temp = """INSERT INTO temp_cmatls_codes (item_code) VALUES (%s)"""

        # Delete records not in the selected item codes
        delete_item = """DELETE FROM sa_task_physical_custom_items WHERE wo_number = %s AND task_number = %s AND item_code NOT IN (SELECT item_code FROM temp_cmatls_codes) AND org_code = %s"""
            
        # Create the temporary table
        cur.execute(create_temp_table)

        # Prepare data for insertion
        item_codes = [
            (material["item_code"])
            for material in passed_data["selected_custom_matls"]
        ]

        # Insert data into the temporary table
        cur.executemany(insert_into_temp, item_codes)
        
        # Perform the DELETE operation
        cur.execute(delete_item, (passed_data["wo_number"], passed_data["task_number"], passed_data["org_code"]))
        

        #--- SAVING COST ESTIMATE ----
        
        # SQL for checking if a record exists
        check_cost = """SELECT COUNT(*) AS count FROM sa_cost_estimates 
                      WHERE wo_number = %s AND org_code = %s"""

        # SQL for inserting a new record
        insert_cost = """INSERT INTO sa_cost_estimates (
                        wo_number, 
                        materials_cost, 
                        total_cost, 
                        created_datetime, 
                        org_code
                        ) VALUES (
                            %s, 
                            %s, 
                            (
                            COALESCE(materials_cost, 0) + 
                            COALESCE(labor_cost, 0) + 
                            COALESCE(equipment_cost, 0) + 
                            COALESCE(overhead_cost, 0) + 
                            COALESCE(contingency_fund, 0)
                            ) - COALESCE(discounts, 0), 
                            %s, 
                            %s
                        )"""
            
        # SQL for updating an existing record
        update_cost = """UPDATE sa_cost_estimates  
                        SET 
                        materials_cost = %s, 
                        total_cost = (
                            COALESCE(materials_cost, 0) + 
                            COALESCE(labor_cost, 0) + 
                            COALESCE(equipment_cost, 0) + 
                            COALESCE(overhead_cost, 0) + 
                            COALESCE(contingency_fund, 0)
                            ) - COALESCE(discounts, 0), 
                        created_datetime = %s 
                        WHERE 
                            wo_number = %s 
                            AND org_code = %s"""

        # Check if the record exists
        cur.execute(check_cost, (passed_data["wo_number"], passed_data["org_code"]))
        result = cur.fetchall()
        

        if result and "count" in result[0]:
            count = result[0]["count"]
            exists = count > 0
        else:
            exists = False

        if exists:
            # Update the existing record
            cur.execute(update_cost, (
                total_materials_cost, now, passed_data["wo_number"], passed_data["org_code"]))
        else:
            # Insert a new record
            cur.execute(insert_cost, (
                passed_data["wo_number"], total_materials_cost, now, passed_data["org_code"]))
        
        
        #--- SAVING HUMAN COMPATIBLE UNITS ---

        # SQL for checking if a record exists
        check_cu = """SELECT COUNT(*) AS count FROM sa_human_compatible_units 
                      WHERE wo_number = %s AND task_number = %s AND cu_code = %s AND org_code = %s"""

        # SQL for inserting a new record
        insert_cu = """INSERT INTO sa_human_compatible_units (wo_number, task_number, cu_code, cu_type, quantity, created_datetime, org_code) 
                       VALUES (%s, %s, %s, %s, %s, %s, %s)"""
                       
        # SQL for updating an existing record
        update_cu = """UPDATE sa_human_compatible_units 
                    SET cu_type = %s, quantity = %s, created_datetime = %s 
                    WHERE wo_number = %s AND task_number = %s AND cu_code = %s AND org_code = %s"""
        
        # Process each selected CU
        for selected_cu in passed_data["selected_human_cus"]:
            cu_code = selected_cu.get("code")
            cu_type = selected_cu.get("type")
            quantity = selected_cu.get("quantity")
            org_code = selected_cu.get("org_code")

            # Check if the record exists
            cur.execute(check_cu, (passed_data["wo_number"], passed_data["task_number"], cu_code, passed_data["org_code"]))
            result = cur.fetchall()

            if result and "count" in result[0]:
                count = result[0]["count"]
                exists = count > 0
            else:
                exists = False

            if exists:
                # Update the existing record
                cur.execute(update_cu, (
                    cu_type, quantity, now, 
                    passed_data["wo_number"], passed_data["task_number"], cu_code, passed_data["org_code"]
                ))
            else:
                # Insert a new record
                cur.execute(insert_cu, (
                    passed_data["wo_number"], passed_data["task_number"], cu_code, cu_type, quantity, now, passed_data["org_code"]
                ))
                
        # Create a temporary table for CU codes
        create_temp_table = """CREATE TEMPORARY TABLE temp_hcu_codes (cu_code VARCHAR(255) NOT NULL)"""

        # Insert CU codes into the temporary table
        insert_into_temp = """INSERT INTO temp_hcu_codes (cu_code) VALUES (%s)"""

        # Delete records not in the selected CU codes
        delete_cu = """DELETE FROM sa_human_compatible_units WHERE wo_number = %s AND task_number = %s AND cu_code NOT IN (SELECT cu_code FROM temp_hcu_codes) AND org_code = %s"""
        
        # Execute: Create the temporary table
        cur.execute(create_temp_table)

        # Execute: Insert CU codes into the temporary table
        cu_codes = [cu["code"] for cu in passed_data["selected_human_cus"]]
        cur.executemany(insert_into_temp, [(code,) for code in cu_codes])
        
        # Execute: Perform the DELETE operation
        cur.execute(delete_cu, (passed_data["wo_number"], passed_data["task_number"], passed_data["org_code"]))

        
        #--- SAVING HUMAN CU LABOR ITEMS ---

        # SQL for checking if a record exists
        check_material = """SELECT COUNT(*) AS count FROM sa_task_human_items 
                            WHERE wo_number = %s AND task_number = %s AND cu_code = %s AND item_code = %s AND org_code = %s"""
                            
        # SQL for inserting a new record
        insert_material = """INSERT INTO sa_task_human_items (wo_number, task_number, item_code, quantity, uom, unit_cost, total_cost, cu_code, created_datetime, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""

        # SQL for updating an existing record
        update_material = """UPDATE sa_task_human_items  
                             SET quantity = %s, unit_cost = %s, total_cost = %s, created_datetime = %s 
                             WHERE wo_number = %s AND task_number = %s AND cu_code = %s AND item_code = %s AND org_code = %s"""
        
        # Process each selected labor items
        for selected_material in passed_data["selected_labors"]:
            cu_code = selected_material.get("cu_code")
            item_code = selected_material.get("item_code")
            quantity = selected_material.get("quantity")
            unit_cost = float(selected_material.get("unit_cost").replace(",", ""))
            total_cost = float(quantity) * unit_cost
            uom = selected_material.get("uom")
            org_code = selected_material.get("org_code")
            total_labor_cost = total_labor_cost + total_cost
            
            # Check if the record exists
            cur.execute(check_material, (passed_data["wo_number"], passed_data["task_number"], cu_code, item_code, passed_data["org_code"]))
            result = cur.fetchall()

            if result and "count" in result[0]:
                count = result[0]["count"]
                exists = count > 0
            else:
                exists = False

            if exists:
                # Update the existing record
                cur.execute(update_material, (
                    quantity, unit_cost, total_cost, now, 
                    passed_data["wo_number"], passed_data["task_number"], cu_code, item_code, passed_data["org_code"]
                ))
            else:
                # Insert a new record
                cur.execute(insert_material, (
                    passed_data["wo_number"], passed_data["task_number"], item_code, quantity, uom, unit_cost, total_cost, cu_code, now, passed_data["org_code"]
                ))

        # Create a temporary table for cu_code and item_code
        create_temp_table = """CREATE TEMPORARY TABLE temp_labors_codes (cu_code VARCHAR(255) NOT NULL,item_code VARCHAR(255) NOT NULL)"""

        # Insert cu_code and item_code into the temporary table
        insert_into_temp = """INSERT INTO temp_labors_codes (cu_code, item_code) VALUES (%s, %s)"""

        # Delete records not in the selected item codes
        delete_item = """DELETE FROM sa_task_human_items WHERE wo_number = %s AND task_number = %s AND CONCAT(cu_code, item_code) NOT IN (SELECT CONCAT(cu_code, item_code) FROM temp_labors_codes) AND org_code = %s"""
            
        # Create the temporary table
        cur.execute(create_temp_table)

        # Prepare data for insertion
        item_codes = [
            (material["cu_code"], material["item_code"])
            for material in passed_data["selected_labors"]
        ]

        # Insert data into the temporary table
        cur.executemany(insert_into_temp, item_codes)
        
        # Perform the DELETE operation
        cur.execute(delete_item, (passed_data["wo_number"], passed_data["task_number"], passed_data["org_code"]))
        
        
        #--- SAVING CU LABOR ALTERATIONS ---
        
        insert_alteration_labor = """INSERT INTO sa_cu_alterations (wo_number, cu_code, alteration, created_datetime, org_code) VALUES (%s, %s, %s, %s, %s)"""
        
        for cu_alteration_labor in passed_data["cu_alterations_labor"]:
            cu_code_labor = cu_alteration_labor.get("cu_code")
            alteration_labor = cu_alteration_labor.get("alteration")
            
            # Insert a new record
            if alteration_labor.strip() != "":
                cur.execute(insert_alteration_labor, (
                        passed_data["wo_number"], cu_code_labor, alteration_labor, now, passed_data["org_code"]
                ))
        
        
        #--- SAVING CUSTOM LABOR ITEMS ---

        # SQL for checking if a record exists
        check_material = """SELECT COUNT(*) AS count FROM sa_task_human_custom_items 
                            WHERE wo_number = %s AND task_number = %s AND item_code = %s AND org_code = %s"""
                            
        # SQL for inserting a new record
        insert_material = """INSERT INTO sa_task_human_custom_items (wo_number, task_number, item_code, quantity, uom, unit_cost, total_cost, created_datetime, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
            
        # SQL for updating an existing record
        update_material = """UPDATE sa_task_human_custom_items  
                             SET quantity = %s, unit_cost = %s, total_cost = %s, created_datetime = %s 
                             WHERE wo_number = %s AND task_number = %s AND item_code = %s AND org_code = %s"""

        # Process each selected labor items
        for selected_material in passed_data["selected_custom_labors"]:
            item_code = selected_material.get("item_code")
            quantity = selected_material.get("quantity")
            unit_cost = float(selected_material.get("unit_cost").replace(",", ""))
            total_cost = float(quantity) * unit_cost
            uom = selected_material.get("uom")
            org_code = selected_material.get("org_code")
            total_labor_cost = total_labor_cost + total_cost
            
            # Check if the record exists
            cur.execute(check_material, (passed_data["wo_number"], passed_data["task_number"], item_code, passed_data["org_code"]))
            result = cur.fetchall()

            if result and "count" in result[0]:
                count = result[0]["count"]
                exists = count > 0
            else:
                exists = False

            if exists:
                # Update the existing record
                cur.execute(update_material, (
                    quantity, unit_cost, total_cost, now, 
                    passed_data["wo_number"], passed_data["task_number"], item_code, passed_data["org_code"]
                ))
            else:
                # Insert a new record
                cur.execute(insert_material, (
                    passed_data["wo_number"], passed_data["task_number"], item_code, quantity, uom, unit_cost, total_cost, now, passed_data["org_code"]
                ))

        # Create a temporary table for cu_code and item_code
        create_temp_table = """CREATE TEMPORARY TABLE temp_hcmatls_codes (item_code VARCHAR(255) NOT NULL)"""

        # Insert cu_code and item_code into the temporary table
        insert_into_temp = """INSERT INTO temp_hcmatls_codes (item_code) VALUES (%s)"""

        # Delete records not in the selected item codes
        delete_item = """DELETE FROM sa_task_human_custom_items WHERE wo_number = %s AND task_number = %s AND item_code NOT IN (SELECT item_code FROM temp_hcmatls_codes) AND org_code = %s"""
        
        # Create the temporary table
        cur.execute(create_temp_table)

        # Prepare data for insertion
        item_codes = [
            (material["item_code"])
            for material in passed_data["selected_custom_labors"]
        ]

        # Insert data into the temporary table
        cur.executemany(insert_into_temp, item_codes)
        
        # Perform the DELETE operation
        cur.execute(delete_item, (passed_data["wo_number"], passed_data["task_number"], passed_data["org_code"]))
        
        
        #--- SAVING LABOR COST ESTIMATE ----
        
        # SQL for checking if a record exists
        check_cost = """SELECT COUNT(*) AS count FROM sa_cost_estimates 
                      WHERE wo_number = %s AND org_code = %s"""
                      
        # SQL for inserting a new record
        insert_cost = """INSERT INTO sa_cost_estimates (
                        wo_number, 
                        labor_cost, 
                        total_cost, 
                        created_datetime, 
                        org_code
                        ) VALUES (
                            %s, 
                            %s, 
                            (
                            COALESCE(materials_cost, 0) + 
                            COALESCE(labor_cost, 0) + 
                            COALESCE(equipment_cost, 0) + 
                            COALESCE(overhead_cost, 0) + 
                            COALESCE(contingency_fund, 0)
                            ) - COALESCE(discounts, 0), 
                            %s, 
                            %s
                        )"""

        # SQL for updating an existing record
        update_cost = """UPDATE sa_cost_estimates  
                        SET 
                        labor_cost = %s, 
                        total_cost = (
                            COALESCE(materials_cost, 0) + 
                            COALESCE(labor_cost, 0) + 
                            COALESCE(equipment_cost, 0) + 
                            COALESCE(overhead_cost, 0) + 
                            COALESCE(contingency_fund, 0)
                            ) - COALESCE(discounts, 0), 
                        created_datetime = %s 
                        WHERE 
                            wo_number = %s 
                            AND org_code = %s"""

        # Check if the record exists
        cur.execute(check_cost, (passed_data["wo_number"], passed_data["org_code"]))
        result = cur.fetchall()
        

        if result and "count" in result[0]:
            count = result[0]["count"]
            exists = count > 0
        else:
            exists = False

        if exists:
            # Update the existing record
            cur.execute(update_cost, (
                total_labor_cost, now, passed_data["wo_number"], passed_data["org_code"]))
        else:
            # Insert a new record
            cur.execute(insert_cost, (
                passed_data["wo_number"], total_labor_cost, now, passed_data["org_code"]))
        
        
        #--- SAVING EQUIPMENT COMPATIBLE UNITS ---

        # SQL for checking if a record exists
        check_cu = """SELECT COUNT(*) AS count FROM sa_equip_compatible_units 
                      WHERE wo_number = %s AND task_number = %s AND cu_code = %s AND org_code = %s"""
                      
        # SQL for inserting a new record
        insert_cu = """INSERT INTO sa_equip_compatible_units (wo_number, task_number, cu_code, cu_type, quantity, created_datetime, org_code) 
                       VALUES (%s, %s, %s, %s, %s, %s, %s)"""
                       
        # SQL for updating an existing record
        update_cu = """UPDATE sa_equip_compatible_units 
                       SET cu_type = %s, quantity = %s, created_datetime = %s 
                       WHERE wo_number = %s AND task_number = %s AND cu_code = %s AND org_code = %s"""
        
        # Process each selected CU
        for selected_cu in passed_data["selected_equip_cus"]:
            cu_code = selected_cu.get("code")
            cu_type = selected_cu.get("type")
            quantity = selected_cu.get("quantity")
            org_code = selected_cu.get("org_code")

            # Check if the record exists
            cur.execute(check_cu, (passed_data["wo_number"], passed_data["task_number"], cu_code, passed_data["org_code"]))
            result = cur.fetchall()

            if result and "count" in result[0]:
                count = result[0]["count"]
                exists = count > 0
            else:
                exists = False

            if exists:
                # Update the existing record
                cur.execute(update_cu, (
                    cu_type, quantity, now, 
                    passed_data["wo_number"], passed_data["task_number"], cu_code, passed_data["org_code"]
                ))
            else:
                # Insert a new record
                cur.execute(insert_cu, (
                    passed_data["wo_number"], passed_data["task_number"], cu_code, cu_type, quantity, now, passed_data["org_code"]
                ))
        
        # Create a temporary table for CU codes
        create_temp_table = """CREATE TEMPORARY TABLE temp_ecu_codes (cu_code VARCHAR(255) NOT NULL)"""

        # Insert CU codes into the temporary table
        insert_into_temp = """INSERT INTO temp_ecu_codes (cu_code) VALUES (%s)"""

        # Delete records not in the selected CU codes
        delete_cu = """DELETE FROM sa_equip_compatible_units WHERE wo_number = %s AND task_number = %s AND cu_code NOT IN (SELECT cu_code FROM temp_ecu_codes) AND org_code = %s"""
        
        # Execute: Create the temporary table
        cur.execute(create_temp_table)

        # Execute: Insert CU codes into the temporary table
        cu_codes = [cu["code"] for cu in passed_data["selected_equip_cus"]]
        cur.executemany(insert_into_temp, [(code,) for code in cu_codes])
        
        # Execute: Perform the DELETE operation
        cur.execute(delete_cu, (passed_data["wo_number"], passed_data["task_number"], passed_data["org_code"]))

        
        #--- SAVING EQUIPMENT CU MATERIALS ---

        # SQL for checking if a record exists
        check_material = """SELECT COUNT(*) AS count FROM sa_task_physical_equip_items 
                            WHERE wo_number = %s AND task_number = %s AND cu_code = %s AND item_code = %s AND org_code = %s"""
                            
        # SQL for inserting a new record
        insert_material = """INSERT INTO sa_task_physical_equip_items (wo_number, task_number, item_code, quantity, uom, unit_cost, total_cost, cu_code, created_datetime, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
        
        # SQL for updating an existing record
        update_material = """UPDATE sa_task_physical_equip_items   
                             SET quantity = %s, unit_cost = %s, total_cost = %s, created_datetime = %s 
                             WHERE wo_number = %s AND task_number = %s AND cu_code = %s AND item_code = %s AND org_code = %s"""
                             
        # Process each selected material
        for selected_material in passed_data["selected_equipment"]:
            cu_code = selected_material.get("cu_code")
            item_code = selected_material.get("item_code")
            quantity = selected_material.get("quantity")
            unit_cost = float(selected_material.get("unit_cost").replace(",", ""))
            total_cost = float(quantity) * unit_cost
            uom = selected_material.get("uom")
            org_code = selected_material.get("org_code")
            total_equipment_cost = total_equipment_cost + total_cost
            
            # Check if the record exists
            cur.execute(check_material, (passed_data["wo_number"], passed_data["task_number"], cu_code, item_code, passed_data["org_code"]))
            result = cur.fetchall()

            if result and "count" in result[0]:
                count = result[0]["count"]
                exists = count > 0
            else:
                exists = False

            if exists:
                # Update the existing record
                cur.execute(update_material, (
                    quantity, unit_cost, total_cost, now, 
                    passed_data["wo_number"], passed_data["task_number"], cu_code, item_code, passed_data["org_code"]
                ))
            else:
                # Insert a new record
                cur.execute(insert_material, (
                    passed_data["wo_number"], passed_data["task_number"], item_code, quantity, uom, unit_cost, total_cost, cu_code, now, passed_data["org_code"]
                ))

        # Create a temporary table for cu_code and item_code
        create_temp_table = """CREATE TEMPORARY TABLE temp_ematls_codes (cu_code VARCHAR(255) NOT NULL,item_code VARCHAR(255) NOT NULL)"""

        # Insert cu_code and item_code into the temporary table
        insert_into_temp = """INSERT INTO temp_ematls_codes (cu_code, item_code) VALUES (%s, %s)"""

        # Delete records not in the selected item codes
        delete_item = """DELETE FROM sa_task_physical_equip_items WHERE wo_number = %s AND task_number = %s AND CONCAT(cu_code, item_code) NOT IN (SELECT CONCAT(cu_code, item_code) FROM temp_ematls_codes) AND org_code = %s"""
            
        # Create the temporary table
        cur.execute(create_temp_table)

        # Prepare data for insertion
        item_codes = [
            (material["cu_code"], material["item_code"])
            for material in passed_data["selected_equipment"]
        ]

        # Insert data into the temporary table
        cur.executemany(insert_into_temp, item_codes)
        
        # Perform the DELETE operation
        cur.execute(delete_item, (passed_data["wo_number"], passed_data["task_number"], passed_data["org_code"]))
        
        
        #--- SAVING CU EQUIPMENT ALTERATIONS ---
        
        insert_alteration_equipment = """INSERT INTO sa_cu_alterations (wo_number, cu_code, alteration, created_datetime, org_code) VALUES (%s, %s, %s, %s, %s)"""
        
        for cu_alteration_equipment in passed_data["cu_alterations_equipment"]:
            cu_code_equipment = cu_alteration_equipment.get("cu_code")
            alteration_equipment = cu_alteration_equipment.get("alteration")
            
            # Insert a new record
            if alteration_equipment.strip() != "":
                cur.execute(insert_alteration_equipment, (
                        passed_data["wo_number"], cu_code_equipment, alteration_equipment, now, passed_data["org_code"]
                ))
        
        
        #--- SAVING EQUIPMENT CUSTOM MATERIALS ---

        # SQL for checking if a record exists
        
        check_material = """SELECT COUNT(*) AS count FROM sa_task_physical_equip_custom_items 
                            WHERE wo_number = %s AND task_number = %s AND item_code = %s AND org_code = %s"""
                            
        # SQL for inserting a new record
        insert_material = """INSERT INTO sa_task_physical_equip_custom_items (wo_number, task_number, item_code, quantity, uom, unit_cost, total_cost, created_datetime, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
            
        # SQL for updating an existing record
        update_material = """UPDATE sa_task_physical_equip_custom_items  
                             SET quantity = %s, unit_cost = %s, total_cost = %s, created_datetime = %s 
                             WHERE wo_number = %s AND task_number = %s AND item_code = %s AND org_code = %s"""
                             
        # Process each selected material
        for selected_material in passed_data["selected_custom_equipment"]:
            item_code = selected_material.get("item_code")
            quantity = selected_material.get("quantity")
            unit_cost = float(selected_material.get("unit_cost").replace(",", ""))
            total_cost = float(quantity) * unit_cost
            uom = selected_material.get("uom")
            org_code = selected_material.get("org_code")
            total_equipment_cost = total_equipment_cost + total_cost
            
            # Check if the record exists
            cur.execute(check_material, (passed_data["wo_number"], passed_data["task_number"], item_code, passed_data["org_code"]))
            result = cur.fetchall()

            if result and "count" in result[0]:
                count = result[0]["count"]
                exists = count > 0
            else:
                exists = False

            if exists:
                # Update the existing record
                cur.execute(update_material, (
                    quantity, unit_cost, total_cost, now, 
                    passed_data["wo_number"], passed_data["task_number"], item_code, passed_data["org_code"]
                ))
            else:
                # Insert a new record
                cur.execute(insert_material, (
                    passed_data["wo_number"], passed_data["task_number"], item_code, quantity, uom, unit_cost, total_cost, now, passed_data["org_code"]
                ))

        # Create a temporary table for cu_code and item_code
        create_temp_table = """CREATE TEMPORARY TABLE temp_ecmatls_codes (item_code VARCHAR(255) NOT NULL)"""

        # Insert cu_code and item_code into the temporary table
        insert_into_temp = """INSERT INTO temp_ecmatls_codes (item_code) VALUES (%s)"""

        # Delete records not in the selected item codes
        delete_item = """DELETE FROM sa_task_physical_equip_custom_items WHERE wo_number = %s AND task_number = %s AND item_code NOT IN (SELECT item_code FROM temp_ecmatls_codes) AND org_code = %s"""
            
        # Create the temporary table
        cur.execute(create_temp_table)

        # Prepare data for insertion
        item_codes = [
            (material["item_code"])
            for material in passed_data["selected_custom_equipment"]
        ]

        # Insert data into the temporary table
        cur.executemany(insert_into_temp, item_codes)
        
        # Perform the DELETE operation
        cur.execute(delete_item, (passed_data["wo_number"], passed_data["task_number"], passed_data["org_code"]))
        

        #--- SAVING EQUIPMENT COST ESTIMATE ----
        
        # SQL for checking if a record exists
        check_cost = """SELECT COUNT(*) AS count FROM sa_cost_estimates 
                      WHERE wo_number = %s AND org_code = %s"""
                      
        # SQL for inserting a new record
        insert_cost = """INSERT INTO sa_cost_estimates (
                        wo_number, 
                        equipment_cost, 
                        total_cost, 
                        created_datetime, 
                        org_code
                        ) VALUES (
                            %s, 
                            %s, 
                            (
                            COALESCE(materials_cost, 0) + 
                            COALESCE(labor_cost, 0) + 
                            COALESCE(equipment_cost, 0) + 
                            COALESCE(overhead_cost, 0) + 
                            COALESCE(contingency_fund, 0)
                            ) - COALESCE(discounts, 0), 
                            %s, 
                            %s
                        )"""
                        
        # SQL for updating an existing record
        update_cost = """UPDATE sa_cost_estimates  
                        SET 
                        equipment_cost = %s, 
                        total_cost = (
                            COALESCE(materials_cost, 0) + 
                            COALESCE(labor_cost, 0) + 
                            COALESCE(equipment_cost, 0) + 
                            COALESCE(overhead_cost, 0) + 
                            COALESCE(contingency_fund, 0)
                            ) - COALESCE(discounts, 0), 
                        created_datetime = %s 
                        WHERE 
                            wo_number = %s 
                            AND org_code = %s"""
                            
        # Check if the record exists
        cur.execute(check_cost, (passed_data["wo_number"], passed_data["org_code"]))
        result = cur.fetchall()
        

        if result and "count" in result[0]:
            count = result[0]["count"]
            exists = count > 0
        else:
            exists = False

        if exists:
            # Update the existing record
            cur.execute(update_cost, (
                total_equipment_cost, now, passed_data["wo_number"], passed_data["org_code"]))
        else:
            # Insert a new record
            cur.execute(insert_cost, (
                passed_data["wo_number"], total_equipment_cost, now, passed_data["org_code"]))
        
        conn.commit()

        # Close the database connection
        cur.close()
        conn.close()

        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True

        # Return success response with 201 status code
        return jsonify({"message": "Operation completed successfully", "result": "posted"}), 201

    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error", "details": str(e)}), 500


#--- save work order updates ----#
@app.route('/updateworkorder', methods=['POST'])
def updateworkorder():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        now = timezone2()
        wo_number = 0
        
        sql1 = """UPDATE work_orders SET wo_description = %s, priority_level = %s, due_date = %s, planner = %s, location = %s, job_start_date = %s, job_end_date = %s WHERE wo_number = %s AND org_code = %s"""
        
        data1 = (passed_data["wo_description"], passed_data["priority_level"], passed_data["due_date"], passed_data["planner"], passed_data["location"], passed_data["job_start_date"], passed_data["job_end_date"], passed_data["wo_number"], passed_data["org_code"])
        
        cur.execute(sql1, data1)
        
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 201 status code
        return jsonify({"message": "Status updated", "result": "updated"}), 201
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500
        

#--- save new standalone master info ----#
@app.route('/postsainfo', methods=['POST'])
def postsainfo():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        now = timezone2()
        
        # SQL for inserting work request data
        sql1 = """INSERT INTO standalone_designs (sa_description, created_datetime, planner, status, org_code) VALUES (%s, %s, %s, %s, %s)"""
        data1 = (passed_data["sa_description"], now, passed_data["planner"], "Open", passed_data["org_code"])
        
        cur.execute(sql1, data1)
        
        # Get the newly created work request id
        sa_number = cur.lastrowid
                
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 201 status code
        return jsonify({"message": "New Record created successfully", "result": sa_number}), 201
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500


#--- save new work log master info ----#
@app.route('/postwlinfo', methods=['POST'])
def postwlinfo():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        now = timezone2()
        
        # SQL for inserting work request data
        sql1 = """INSERT INTO work_logs (email_address, title, log_datetime, status, org_code) VALUES (%s, %s, %s, %s, %s)"""
        data1 = (passed_data["email_address"], passed_data["title"], now, passed_data["status"], passed_data["org_code"])
        
        cur.execute(sql1, data1)
        
        # Get the newly created work request id
        wl_number = cur.lastrowid
                
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 201 status code
        return jsonify({"message": "New Record created successfully", "result": wl_number}), 201
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500


#--- save standalone master info updates ----#
@app.route('/updatesainfo', methods=['POST'])
def updatesainfo():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        now = timezone2()
        wo_number = 0
        
        sql1 = """UPDATE standalone_designs SET sa_description = %s, planner = %s WHERE sa_number = %s AND org_code = %s"""
        
        data1 = (passed_data["sa_description"], passed_data["planner"], passed_data["sa_number"], passed_data["org_code"])
        
        cur.execute(sql1, data1)
        
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 201 status code
        return jsonify({"message": "Info updated", "result": "updated"}), 201
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500


#--- save work log master info updates ----#
@app.route('/updatewlinfo', methods=['POST'])
def updatewlinfo():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        now = timezone2()
        wo_number = 0
        
        sql1 = """UPDATE work_logs SET title = %s WHERE id = %s AND org_code = %s"""
        
        data1 = (passed_data["title"], passed_data["id"], passed_data["org_code"])
        
        cur.execute(sql1, data1)
        
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 201 status code
        return jsonify({"message": "Info updated", "result": "updated"}), 201
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500


#--- save new timesheet entry ----#
@app.route('/posttimesheet', methods=['POST'])
def posttimesheet():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        now = timezone2()
        
        # SQL for inserting entries
        insert_entry = """INSERT INTO timesheets (work_log_id, email_address, task, start, end, hours, created_datetime, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"""

        # Process entries array
        for entry in passed_data["entries"]:
            tasktitle = entry.get("task")
            task_start = entry.get("start")
            task_end = entry.get("end")
            duration_str = entry.get("duration")  # e.g., "24h 0m" or "2h 30m"
    
            # Use regex to extract hours and minutes
            hours_match = re.search(r"(\d+)\s*h", duration_str)
            minutes_match = re.search(r"(\d+)\s*m", duration_str)
            
            if hours_match:
                hours = Decimal(hours_match.group(1))
            else:
                hours = Decimal("0")
            
            if minutes_match:
                minutes = Decimal(minutes_match.group(1))
            else:
                minutes = Decimal("0")
            
            # Convert minutes to hours
            minutes_as_hours = minutes / Decimal("60")
            task_hrs = hours + minutes_as_hours
            
            cur.execute(insert_entry, (passed_data["work_log_id"], passed_data["email_address"], tasktitle, task_start, task_end, task_hrs, now, passed_data["org_code"]))

        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 201 status code
        return jsonify({"message": "New Timesheet Entries created successfully", "result": "inserted"}), 201
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500


#--- save new supplier ----#
@app.route('/postnewsupplier', methods=['POST'])
def postnewsupplier():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        now = timezone2()
        
        # SQL for inserting supplier data
        sql1 = """INSERT INTO suppliers (name, primary_contact, contact_numbers, email_address, website, office_address, tax_identification_number, payment_terms, credit_limit_terms, industry, created_datetime, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
        data1 = (passed_data["name"], passed_data["primary_contact"], passed_data["contact_numbers"], passed_data["email_address"], passed_data["website"], passed_data["office_address"], passed_data["tin"], passed_data["payment_terms"], passed_data["credit_limit_terms"], passed_data["industry"], now, passed_data["org_code"])
        
        cur.execute(sql1, data1)
        
        # Get the newly created work request id
        supplier_id = cur.lastrowid
                
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 201 status code
        return jsonify({"message": "New Record created successfully", "result": "inserted"}), 201
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500


#--- save new material ----#
@app.route('/postnewmaterial', methods=['POST'])
def postnewmaterial():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        now = timezone2()
        
        # SQL for inserting supplier data
        sql1 = """INSERT INTO physical_items (description, unit_cost, unit_cost_low, unit_cost_avg, category, unit_of_measure, status, updated_datetime, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
        data1 = (passed_data["description"], passed_data["unit_cost_high"], passed_data["unit_cost_low"], passed_data["unit_cost_avg"], passed_data["category"], passed_data["uom"], 1, now, passed_data["org_code"])
        
        cur.execute(sql1, data1)
        
        # Get the newly created work request id
        supplier_id = cur.lastrowid
                
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 201 status code
        return jsonify({"message": "New Record created successfully", "result": "inserted"}), 201
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500


#--- save new labor ----#
@app.route('/postnewlabor', methods=['POST'])
def postnewlabor():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        now = timezone2()
        
        # SQL for inserting supplier data
        sql1 = """INSERT INTO human_items (description, unit_cost, unit_cost_low, unit_cost_avg, category, unit_of_measure, status, updated_datetime, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
        data1 = (passed_data["description"], passed_data["unit_cost_high"], passed_data["unit_cost_low"], passed_data["unit_cost_avg"], passed_data["category"], passed_data["uom"], 1, now, passed_data["org_code"])
        
        cur.execute(sql1, data1)
        
        # Get the newly created work request id
        supplier_id = cur.lastrowid
                
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 201 status code
        return jsonify({"message": "New Record created successfully", "result": "inserted"}), 201
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500


#--- save new equipment ----#
@app.route('/postnewequipment', methods=['POST'])
def postnewequipment():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        now = timezone2()
        
        # SQL for inserting supplier data
        sql1 = """INSERT INTO physical_equip_items (description, unit_cost, unit_cost_low, unit_cost_avg, category, unit_of_measure, status, updated_datetime, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
        data1 = (passed_data["description"], passed_data["unit_cost_high"], passed_data["unit_cost_low"], passed_data["unit_cost_avg"], passed_data["category"], passed_data["uom"], 1, now, passed_data["org_code"])
        
        cur.execute(sql1, data1)
        
        # Get the newly created work request id
        supplier_id = cur.lastrowid
                
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 201 status code
        return jsonify({"message": "New Record created successfully", "result": "inserted"}), 201
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500


#--- save new Material CU ----#
@app.route('/postnewmaterialcu', methods=['POST'])
def postnewmaterialcu():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        now = timezone2()

        cu_code = get_next_cu_code("MAT")
        
        # SQL for inserting supplier data
        sql1 = """INSERT INTO physical_compatible_units (code, title, description, quantity, type, category, status, updated_datetime, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
        data1 = (cu_code, passed_data["title"], passed_data["description"], 1, 'M',passed_data["category"], 1, now, passed_data["org_code"])
        
        cur.execute(sql1, data1)
                
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 201 status code
        return jsonify({"message": "New Record created successfully", "result": "inserted"}), 201
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500


#--- save new Labor CU ----#
@app.route('/postnewlaborcu', methods=['POST'])
def postnewlaborcu():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        now = timezone2()

        cu_code = get_next_cu_code("LAB")
        
        # SQL for inserting supplier data
        sql1 = """INSERT INTO human_compatible_units (code, title, description, quantity, type, category, status, updated_datetime, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
        data1 = (cu_code, passed_data["title"], passed_data["description"], 1, 'L',passed_data["category"], 1, now, passed_data["org_code"])
        
        cur.execute(sql1, data1)
                
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 201 status code
        return jsonify({"message": "New Record created successfully", "result": "inserted"}), 201
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500
    

#--- save new Equipment CU ----#
@app.route('/postnewequipmentcu', methods=['POST'])
def postnewequipmentcu():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        now = timezone2()

        cu_code = get_next_cu_code("EQU")
        
        # SQL for inserting supplier data
        sql1 = """INSERT INTO physical_equip_compatible_units (code, title, description, quantity, type, category, status, updated_datetime, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
        data1 = (cu_code, passed_data["title"], passed_data["description"], 1, 'E',passed_data["category"], 1, now, passed_data["org_code"])
        
        cur.execute(sql1, data1)
                
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 201 status code
        return jsonify({"message": "New Record created successfully", "result": "inserted"}), 201
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500


#--- save new material CU category ----#
@app.route('/postnewmaterialcucategory', methods=['POST'])
def postnewmaterialcucategory():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        now = timezone2()

        cucat_code = get_next_cu_category_code()
        
        # SQL for inserting category data
        sql1 = """INSERT INTO physical_cu_categories (category, title, status, org_code) VALUES (%s, %s, %s, %s)"""
        data1 = (cucat_code, passed_data["category_title"], 1, passed_data["org_code"])
        
        cur.execute(sql1, data1)
                
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 201 status code
        return jsonify({"message": "New Record created successfully", "result": "inserted"}), 201
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500


#--- save new labor CU category ----#
@app.route('/postnewlaborcucategory', methods=['POST'])
def postnewlaborcucategory():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        now = timezone2()

        cucat_code = get_next_cu_category_code()
        
        # SQL for inserting category data
        sql1 = """INSERT INTO human_cu_categories (category, title, status, org_code) VALUES (%s, %s, %s, %s)"""
        data1 = (cucat_code, passed_data["category_title"], 1, passed_data["org_code"])
        
        cur.execute(sql1, data1)
                
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 201 status code
        return jsonify({"message": "New Record created successfully", "result": "inserted"}), 201
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500


#--- save new equipment CU category ----#
@app.route('/postnewequipmentcucategory', methods=['POST'])
def postnewequipmentcucategory():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        now = timezone2()

        cucat_code = get_next_cu_category_code()
        
        # SQL for inserting category data
        sql1 = """INSERT INTO equip_cu_categories (category, title, status, org_code) VALUES (%s, %s, %s, %s)"""
        data1 = (cucat_code, passed_data["category_title"], 1, passed_data["org_code"])
        
        cur.execute(sql1, data1)
                
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 201 status code
        return jsonify({"message": "New Record created successfully", "result": "inserted"}), 201
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500


#--- save new material item category ----#
@app.route('/postnewmaterialitemcategory', methods=['POST'])
def postnewmaterialitemcategory():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        now = timezone2()
        
        # SQL for inserting category data
        sql1 = """INSERT INTO physical_item_categories (description, status, org_code) VALUES (%s, %s, %s)"""
        data1 = (passed_data["category_title"], 1, passed_data["org_code"])
        
        cur.execute(sql1, data1)
                
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 201 status code
        return jsonify({"message": "New Record created successfully", "result": "inserted"}), 201
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500


#--- save new labor item category ----#
@app.route('/postnewlaboritemcategory', methods=['POST'])
def postnewlaboritemcategory():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        now = timezone2()
        
        # SQL for inserting category data
        sql1 = """INSERT INTO human_item_categories (description, status, org_code) VALUES (%s, %s, %s)"""
        data1 = (passed_data["category_title"], 1, passed_data["org_code"])
        
        cur.execute(sql1, data1)
                
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 201 status code
        return jsonify({"message": "New Record created successfully", "result": "inserted"}), 201
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500


#--- save new equipment item category ----#
@app.route('/postnewequipmentitemcategory', methods=['POST'])
def postnewequipmentitemcategory():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        now = timezone2()
        
        # SQL for inserting category data
        sql1 = """INSERT INTO equip_item_categories (description, status, org_code) VALUES (%s, %s, %s)"""
        data1 = (passed_data["category_title"], 1, passed_data["org_code"])
        
        cur.execute(sql1, data1)
                
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 201 status code
        return jsonify({"message": "New Record created successfully", "result": "inserted"}), 201
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500
    

#--- save new business unit ----#
@app.route('/postnewbusinessunit', methods=['POST'])
def postnewbusinessunit():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        now = timezone2()

        bu_code = get_next_business_unit_code()
        
        # SQL for inserting row
        sql1 = """INSERT INTO business_units (code, description, status, org_code) VALUES (%s, %s, %s, %s)"""
        data1 = (bu_code, passed_data["description"], 1, passed_data["org_code"])
        
        cur.execute(sql1, data1)
                
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 201 status code
        return jsonify({"message": "New Record created successfully", "result": "inserted"}), 201
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500


#--- save new planner ----#
@app.route('/postnewplanner', methods=['POST'])
def postnewplanner():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        now = timezone2()
        
        # SQL for inserting row
        sql1 = """INSERT INTO planners (name, email_address, status, org_code) VALUES (%s, %s, %s, %s)"""
        data1 = (passed_data["name"], passed_data["email_address"], 1, passed_data["org_code"])
        
        cur.execute(sql1, data1)
                
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 201 status code
        return jsonify({"message": "New Record created successfully", "result": "inserted"}), 201
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500
    

#--- save assigned materials entry ----#
@app.route('/postassignedmaterials', methods=['POST'])
def postassignedmaterials():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        now = timezone2()
        
        check_material = """SELECT COUNT(*) AS count FROM supplier_materials 
                            WHERE supplier_id = %s AND item_code = %s AND org_code = %s"""
                            
        # SQL for inserting materials
        insert_material = """INSERT INTO supplier_materials (supplier_id, item_code, created_datetime, org_code) VALUES (%s, %s, %s, %s)"""
        
        # SQL for updating an existing record
        update_material = """UPDATE supplier_materials   
                             SET created_datetime = %s 
                             WHERE supplier_id = %s AND item_code = %s AND org_code = %s"""

        # Process assigned materials array
        for material in passed_data["assigned_materials"]:
            item_code = material.get("item_code")
            
            # Check if the record exists
            cur.execute(check_material, (passed_data["supplier_id"], item_code, passed_data["org_code"]))
            result = cur.fetchall()

            if result and "count" in result[0]:
                count = result[0]["count"]
                exists = count > 0
            else:
                exists = False

            if exists:
                # Update the existing record
                cur.execute(update_material, (now, 
                    passed_data["supplier_id"], item_code, passed_data["org_code"]
                ))
            else:
                # Insert a new record
                cur.execute(insert_material, (
                    passed_data["supplier_id"], item_code, now, passed_data["org_code"]
                ))

        # Create a temporary table for item_code
        create_temp_table = """CREATE TEMPORARY TABLE temp_matls_assigns (item_code INT NOT NULL)"""

        # Insert item_code into the temporary table
        insert_into_temp = """INSERT INTO temp_matls_assigns (item_code) VALUES (%s)"""

        # Delete records not in the selected item codes
        delete_item = """DELETE FROM supplier_materials WHERE supplier_id = %s AND  item_code NOT IN (SELECT item_code FROM temp_matls_assigns) AND org_code = %s"""
            
        # Create the temporary table
        cur.execute(create_temp_table)

        # Prepare data for insertion
        item_codes = [
            (material["item_code"])
            for material in passed_data["assigned_materials"]
        ]

        # Insert data into the temporary table
        cur.executemany(insert_into_temp, item_codes)
        
        # Perform the DELETE operation
        cur.execute(delete_item, (passed_data["supplier_id"], passed_data["org_code"]))
            
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 201 status code
        return jsonify({"message": "Materials assignment created successfully", "result": "inserted"}), 201
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500


#--- save CU assigned materials entry ----#
@app.route('/postcuassignedmaterials', methods=['POST'])
def postcuassignedmaterials():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        now = timezone2()
        
        check_material = """SELECT COUNT(*) AS count FROM physical_cu_items 
                            WHERE cu_code = %s AND item_code = %s AND org_code = %s"""
                            
        # SQL for inserting materials
        insert_material = """INSERT INTO physical_cu_items (cu_code, item_code, quantity, unit_of_measure, status, updated_datetime, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s)"""
        
        # SQL for updating an existing record
        update_material = """UPDATE physical_cu_items 
                             SET quantity = %s, updated_datetime = %s 
                             WHERE cu_code = %s AND item_code = %s AND org_code = %s"""

        
        # Process assigned materials array
        for material in passed_data["assigned_materials"]:
            item_code = material.get("item_code")
            quantity = material.get("quantity")
            uom = material.get("uom")
            
            # Check if the record exists
            cur.execute(check_material, (passed_data["cu_code"], item_code, passed_data["org_code"]))
            result = cur.fetchall()

            if result and "count" in result[0]:
                count = result[0]["count"]
                exists = count > 0
            else:
                exists = False

            if exists:
                # Update the existing record
                cur.execute(update_material, (quantity, now, 
                    passed_data["cu_code"], item_code, passed_data["org_code"]
                ))
            else:
                # Insert a new record
                cur.execute(insert_material, (
                    passed_data["cu_code"], item_code, quantity, uom, 1, now, passed_data["org_code"]
                ))

        # Create a temporary table for item_code
        create_temp_table = """CREATE TEMPORARY TABLE temp_matls_assigns (item_code INT NOT NULL)"""

        # Insert item_code into the temporary table
        insert_into_temp = """INSERT INTO temp_matls_assigns (item_code) VALUES (%s)"""

        # Delete records not in the selected item codes
        delete_item = """DELETE FROM physical_cu_items WHERE cu_code = %s AND item_code NOT IN (SELECT item_code FROM temp_matls_assigns) AND org_code = %s"""
            
        # Create the temporary table
        cur.execute(create_temp_table)

        # Prepare data for insertion
        item_codes = [
            (material["item_code"])
            for material in passed_data["assigned_materials"]
        ]

        # Insert data into the temporary table
        cur.executemany(insert_into_temp, item_codes)
        
        # Perform the DELETE operation
        cur.execute(delete_item, (passed_data["cu_code"], passed_data["org_code"]))
            
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 201 status code
        return jsonify({"message": "Materials assignment created successfully", "result": "inserted"}), 201
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500


#--- save CU assigned labors entry ----#
@app.route('/postcuassignedlabors', methods=['POST'])
def postcuassignedlabors():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        now = timezone2()
        
        check_material = """SELECT COUNT(*) AS count FROM human_cu_items 
                            WHERE cu_code = %s AND item_code = %s AND org_code = %s"""
                            
        # SQL for inserting materials
        insert_material = """INSERT INTO human_cu_items (cu_code, item_code, quantity, unit_of_measure, status, updated_datetime, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s)"""
        
        # SQL for updating an existing record
        update_material = """UPDATE human_cu_items 
                             SET quantity = %s, updated_datetime = %s 
                             WHERE cu_code = %s AND item_code = %s AND org_code = %s"""

        
        # Process assigned materials array
        for material in passed_data["assigned_materials"]:
            item_code = material.get("item_code")
            quantity = material.get("quantity")
            uom = material.get("uom")
            
            # Check if the record exists
            cur.execute(check_material, (passed_data["cu_code"], item_code, passed_data["org_code"]))
            result = cur.fetchall()

            if result and "count" in result[0]:
                count = result[0]["count"]
                exists = count > 0
            else:
                exists = False

            if exists:
                # Update the existing record
                cur.execute(update_material, (quantity, now, 
                    passed_data["cu_code"], item_code, passed_data["org_code"]
                ))
            else:
                # Insert a new record
                cur.execute(insert_material, (
                    passed_data["cu_code"], item_code, quantity, uom, 1, now, passed_data["org_code"]
                ))

        # Create a temporary table for item_code
        create_temp_table = """CREATE TEMPORARY TABLE temp_matls_assigns (item_code INT NOT NULL)"""

        # Insert item_code into the temporary table
        insert_into_temp = """INSERT INTO temp_matls_assigns (item_code) VALUES (%s)"""

        # Delete records not in the selected item codes
        delete_item = """DELETE FROM human_cu_items WHERE cu_code = %s AND item_code NOT IN (SELECT item_code FROM temp_matls_assigns) AND org_code = %s"""
            
        # Create the temporary table
        cur.execute(create_temp_table)

        # Prepare data for insertion
        item_codes = [
            (material["item_code"])
            for material in passed_data["assigned_materials"]
        ]

        # Insert data into the temporary table
        cur.executemany(insert_into_temp, item_codes)
        
        # Perform the DELETE operation
        cur.execute(delete_item, (passed_data["cu_code"], passed_data["org_code"]))
            
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 201 status code
        return jsonify({"message": "Labors assignment created successfully", "result": "inserted"}), 201
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500


#--- save CU assigned equipment entry ----#
@app.route('/postcuassignedequipment', methods=['POST'])
def postcuassignedequipment():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        now = timezone2()
        
        check_material = """SELECT COUNT(*) AS count FROM physical_equip_cu_items 
                            WHERE cu_code = %s AND item_code = %s AND org_code = %s"""
                            
        # SQL for inserting materials
        insert_material = """INSERT INTO physical_equip_cu_items (cu_code, item_code, quantity, unit_of_measure, status, updated_datetime, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s)"""
        
        # SQL for updating an existing record
        update_material = """UPDATE physical_equip_cu_items 
                             SET quantity = %s, updated_datetime = %s 
                             WHERE cu_code = %s AND item_code = %s AND org_code = %s"""

        
        # Process assigned materials array
        for material in passed_data["assigned_materials"]:
            item_code = material.get("item_code")
            quantity = material.get("quantity")
            uom = material.get("uom")
            
            # Check if the record exists
            cur.execute(check_material, (passed_data["cu_code"], item_code, passed_data["org_code"]))
            result = cur.fetchall()

            if result and "count" in result[0]:
                count = result[0]["count"]
                exists = count > 0
            else:
                exists = False

            if exists:
                # Update the existing record
                cur.execute(update_material, (quantity, now, 
                    passed_data["cu_code"], item_code, passed_data["org_code"]
                ))
            else:
                # Insert a new record
                cur.execute(insert_material, (
                    passed_data["cu_code"], item_code, quantity, uom, 1, now, passed_data["org_code"]
                ))

        # Create a temporary table for item_code
        create_temp_table = """CREATE TEMPORARY TABLE temp_matls_assigns (item_code INT NOT NULL)"""

        # Insert item_code into the temporary table
        insert_into_temp = """INSERT INTO temp_matls_assigns (item_code) VALUES (%s)"""

        # Delete records not in the selected item codes
        delete_item = """DELETE FROM physical_equip_cu_items WHERE cu_code = %s AND item_code NOT IN (SELECT item_code FROM temp_matls_assigns) AND org_code = %s"""
            
        # Create the temporary table
        cur.execute(create_temp_table)

        # Prepare data for insertion
        item_codes = [
            (material["item_code"])
            for material in passed_data["assigned_materials"]
        ]

        # Insert data into the temporary table
        cur.executemany(insert_into_temp, item_codes)
        
        # Perform the DELETE operation
        cur.execute(delete_item, (passed_data["cu_code"], passed_data["org_code"]))
            
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 201 status code
        return jsonify({"message": "Equipment assignment created successfully", "result": "inserted"}), 201
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500


#--- delete timesheet entry ----#
@app.route('/deletetimeentry', methods=['DELETE'])
def deletetimeentry():
    if 'row_id' in request.args:
        row_id = request.args['row_id']
    else:
        return "Error: No Row ID field provided. Please specify it."
        
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        now = timezone2()
        
        # SQL for inserting entries
        delete_entry = """DELETE FROM timesheets WHERE id = %s AND org_code = %s"""
        cur.execute(delete_entry, (row_id, org_code))

        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 201 status code
        return jsonify({"message": "Time Entry deleted successfully", "result": "deleted"}), 200
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500


# Saving changes on user roles list
@app.route('/saveuserroleslist', methods=['PUT'])
def saveuserroleslist():
    import traceback
    
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()

        user_name = passed_data.get('user_name')
        roles_list = passed_data.get('roles_list')
        org_code = passed_data.get('org_code')

        if not user_name or not roles_list or not org_code:
            return jsonify({"error": "Missing required fields"}), 400
        
        new_roles = [role_item['role'] for role_item in roles_list if 'role' in role_item]

        cur.execute("""
            SELECT role FROM app_user_roles
            WHERE `user` = %s AND org_code = %s
        """, (user_name, org_code))
        
        existing_roles = [row['role'] for row in cur.fetchall()]
        
        # Delete roles not in new list
        roles_to_delete = list(set(existing_roles) - set(new_roles))
        if roles_to_delete:
            placeholders = ','.join(['%s'] * len(roles_to_delete))
            delete_query = f"""
                DELETE FROM app_user_roles
                WHERE `user` = %s AND org_code = %s AND role IN ({placeholders})
            """
            params = (user_name, org_code) + tuple(roles_to_delete)
            cur.execute(delete_query, params)
            

        # Insert new roles
        roles_to_insert = list(set(new_roles) - set(existing_roles))
        insert_query = """
            INSERT INTO app_user_roles (`user`, role, status, org_code)
            VALUES (%s, %s, %s, %s)
        """
        for role in roles_to_insert:
            cur.execute(insert_query, (user_name, role, 1, org_code))
            

        conn.commit()

        cur.close()
        conn.close()

        return jsonify({"message": "Updated successfully", "result": "updated"}), 200

    except Exception as e:
        logger.error(f"Error saving user roles: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": "Internal server error"}), 500


# update app user FCM token
@app.route('/savefcmtoken', methods=['PUT'])
def savefcmtoken():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        now = timezone2()  # Ensure this function returns the current datetime
        
        # SQL for updating read datetime in app_inbox
        sql1 = """UPDATE app_users SET fcm_token = %s WHERE user = %s AND org_code = %s"""
        data1 = (passed_data["fcm_token"], passed_data["user_id"], passed_data["org_code"])  
        
        cur.execute(sql1, data1)
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 200 status code
        return jsonify({"message": "Updated successfully", "result": "updated"}), 200
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500


# update customer info change
@app.route('/updatecustomer', methods=['PUT'])
def updatecustomer():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        org_code = passed_data.get('org_code')
        
        now = timezone2()  # Ensure this function returns the current datetime
        
        sql1 = """UPDATE customers SET firstname = %s, middlename = %s, lastname = %s, email_address = %s, contact_number = %s, street_address = %s, city = %s, province = %s, company_name = %s, created_datetime = %s WHERE id = %s AND org_code = %s"""
        data1 = (passed_data["firstname"], passed_data["middlename"], passed_data["lastname"], passed_data["email_address"], passed_data["contact_number"], passed_data["street_address"], passed_data["city"], passed_data["province"], passed_data["company_name"], now, passed_data["id"], org_code)  
        
        cur.execute(sql1, data1)
        
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 200 status code
        return jsonify({"message": "Updated successfully", "result": "updated"}), 200
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500


# update supplier info change
@app.route('/updatesupplier', methods=['PUT'])
def updatesupplier():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        org_code = passed_data.get('org_code')
        
        now = timezone2()  # Ensure this function returns the current datetime
        
        sql1 = """UPDATE suppliers SET name = %s, primary_contact = %s, contact_numbers = %s, email_address = %s, website = %s, office_address = %s, tax_identification_number = %s, payment_terms = %s, credit_limit_terms = %s, industry = %s, created_datetime = %s WHERE id = %s AND org_code = %s"""
        data1 = (passed_data["name"], passed_data["primary_contact"], passed_data["contact_numbers"], passed_data["email_address"], passed_data["website"], passed_data["office_address"], passed_data["tin"], passed_data["payment_terms"], passed_data["credit_limit_terms"], passed_data["industry"], now, passed_data["id"], org_code)  
        
        cur.execute(sql1, data1)
        
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 200 status code
        return jsonify({"message": "Updated successfully", "result": "updated"}), 200
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500


# update material info change
@app.route('/updatematerial', methods=['PUT'])
def updatematerial():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        org_code = passed_data.get('org_code')
        
        now = timezone2()  # Ensure this function returns the current datetime
        
        sql1 = """UPDATE physical_items SET description = %s, unit_cost = %s, unit_cost_low = %s, unit_cost_avg = %s, unit_of_measure = %s, category = %s, updated_datetime = %s  WHERE item_code = %s AND org_code = %s"""
        data1 = (passed_data["description"], passed_data["unit_cost_high"], passed_data["unit_cost_low"], passed_data["unit_cost_avg"], passed_data["unit_of_measure"], passed_data["category"], now, passed_data["item_code"], org_code)  
        
        cur.execute(sql1, data1)
        
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 200 status code
        return jsonify({"message": "Updated successfully", "result": "updated"}), 200
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500


# update labor info change
@app.route('/updatelabor', methods=['PUT'])
def updatelabor():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        org_code = passed_data.get('org_code')
        
        now = timezone2()  # Ensure this function returns the current datetime
        
        sql1 = """UPDATE human_items SET description = %s, unit_cost = %s, unit_cost_low = %s, unit_cost_avg = %s, unit_of_measure = %s, category = %s, updated_datetime = %s  WHERE item_code = %s AND org_code = %s"""
        data1 = (passed_data["description"], passed_data["unit_cost_high"], passed_data["unit_cost_low"], passed_data["unit_cost_avg"], passed_data["unit_of_measure"], passed_data["category"], now, passed_data["item_code"], org_code)  
        
        cur.execute(sql1, data1)
        
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 200 status code
        return jsonify({"message": "Updated successfully", "result": "updated"}), 200
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500
    

# update equipment info change
@app.route('/updateequipment', methods=['PUT'])
def updateequipment():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        org_code = passed_data.get('org_code')
        
        now = timezone2()  # Ensure this function returns the current datetime
        
        sql1 = """UPDATE physical_equip_items SET description = %s, unit_cost = %s, unit_cost_low = %s, unit_cost_avg = %s, unit_of_measure = %s, category = %s, updated_datetime = %s  WHERE item_code = %s AND org_code = %s"""
        data1 = (passed_data["description"], passed_data["unit_cost_high"], passed_data["unit_cost_low"], passed_data["unit_cost_avg"], passed_data["unit_of_measure"], passed_data["category"], now, passed_data["item_code"], org_code)  
        
        cur.execute(sql1, data1)
        
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 200 status code
        return jsonify({"message": "Updated successfully", "result": "updated"}), 200
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500


# update material CU info changes
@app.route('/updatematerialcuinfo', methods=['PUT'])
def updatematerialcuinfo():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        org_code = passed_data.get('org_code')
        
        now = timezone2()  # Ensure this function returns the current datetime
        
        sql1 = """UPDATE physical_compatible_units SET title = %s, description = %s, category = %s, updated_datetime = %s WHERE code = %s AND org_code = %s"""
        data1 = (passed_data["title"], passed_data["description"], passed_data["category"], now, passed_data["cu_code"], org_code)  
        
        cur.execute(sql1, data1)
        
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 200 status code
        return jsonify({"message": "Updated successfully", "result": "updated"}), 200
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500
    

# update labor CU info changes
@app.route('/updatelaborcuinfo', methods=['PUT'])
def updatelaborcuinfo():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        org_code = passed_data.get('org_code')
        
        now = timezone2()  # Ensure this function returns the current datetime
        
        sql1 = """UPDATE human_compatible_units SET title = %s, description = %s, category = %s, updated_datetime = %s WHERE code = %s AND org_code = %s"""
        data1 = (passed_data["title"], passed_data["description"], passed_data["category"], now, passed_data["cu_code"], org_code)  
        
        cur.execute(sql1, data1)
        
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 200 status code
        return jsonify({"message": "Updated successfully", "result": "updated"}), 200
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500


# update equipment CU info changes
@app.route('/updateequipmentcuinfo', methods=['PUT'])
def updateequipmentcuinfo():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        org_code = passed_data.get('org_code')
        
        now = timezone2()  # Ensure this function returns the current datetime
        
        sql1 = """UPDATE physical_equip_compatible_units SET title = %s, description = %s, category = %s, updated_datetime = %s WHERE code = %s AND org_code = %s"""
        data1 = (passed_data["title"], passed_data["description"], passed_data["category"], now, passed_data["cu_code"], org_code)  
        
        cur.execute(sql1, data1)
        
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 200 status code
        return jsonify({"message": "Updated successfully", "result": "updated"}), 200
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500


# update Material CU Category info changes
@app.route('/updatematerialcucategoryinfo', methods=['PUT'])
def updatematerialcucategoryinfo():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        org_code = passed_data.get('org_code')
        
        now = timezone2()  # Ensure this function returns the current datetime
        
        sql1 = """UPDATE physical_cu_categories SET title = %s WHERE category = %s AND org_code = %s"""
        data1 = (passed_data["title"], passed_data["category"], org_code)  
        
        cur.execute(sql1, data1)
        
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 200 status code
        return jsonify({"message": "Updated successfully", "result": "updated"}), 200
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500


# update Labor CU Category info changes
@app.route('/updatelaborcucategoryinfo', methods=['PUT'])
def updatelaborcucategoryinfo():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        org_code = passed_data.get('org_code')
        
        now = timezone2()  # Ensure this function returns the current datetime
        
        sql1 = """UPDATE human_cu_categories SET title = %s WHERE category = %s AND org_code = %s"""
        data1 = (passed_data["title"], passed_data["category"], org_code)  
        
        cur.execute(sql1, data1)
        
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 200 status code
        return jsonify({"message": "Updated successfully", "result": "updated"}), 200
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500
    

# update Equipment CU Category info changes
@app.route('/updateequipmentcucategoryinfo', methods=['PUT'])
def updateequipmentcucategoryinfo():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        org_code = passed_data.get('org_code')
        
        now = timezone2()  # Ensure this function returns the current datetime
        
        sql1 = """UPDATE equip_cu_categories SET title = %s WHERE category = %s AND org_code = %s"""
        data1 = (passed_data["title"], passed_data["category"], org_code)  
        
        cur.execute(sql1, data1)
        
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 200 status code
        return jsonify({"message": "Updated successfully", "result": "updated"}), 200
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500


# update Material Item Category info changes
@app.route('/updatematerialitemcategoryinfo', methods=['PUT'])
def updatematerialitemcategoryinfo():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        org_code = passed_data.get('org_code')
        
        now = timezone2()  # Ensure this function returns the current datetime
        
        sql1 = """UPDATE physical_item_categories SET description = %s WHERE id = %s AND org_code = %s"""
        data1 = (passed_data["description"], passed_data["id"], org_code)  
        
        cur.execute(sql1, data1)
        
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 200 status code
        return jsonify({"message": "Updated successfully", "result": "updated"}), 200
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500


# update Labor Item Category info changes
@app.route('/updatelaboritemcategoryinfo', methods=['PUT'])
def updatelaboritemcategoryinfo():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        org_code = passed_data.get('org_code')
        
        now = timezone2()  # Ensure this function returns the current datetime
        
        sql1 = """UPDATE human_item_categories SET description = %s WHERE id = %s AND org_code = %s"""
        data1 = (passed_data["description"], passed_data["id"], org_code)  
        
        cur.execute(sql1, data1)
        
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 200 status code
        return jsonify({"message": "Updated successfully", "result": "updated"}), 200
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500


# update Equipment Item Category info changes
@app.route('/updateequipmentitemcategoryinfo', methods=['PUT'])
def updateequipmentitemcategoryinfo():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        org_code = passed_data.get('org_code')
        
        now = timezone2()  # Ensure this function returns the current datetime
        
        sql1 = """UPDATE equip_item_categories SET description = %s WHERE id = %s AND org_code = %s"""
        data1 = (passed_data["description"], passed_data["id"], org_code)  
        
        cur.execute(sql1, data1)
        
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 200 status code
        return jsonify({"message": "Updated successfully", "result": "updated"}), 200
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500
    

# update Business Unit info changes
@app.route('/updatebusinessunitinfo', methods=['PUT'])
def updatebusinessunitinfo():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        org_code = passed_data.get('org_code')
        
        now = timezone2()  # Ensure this function returns the current datetime
        
        sql1 = """UPDATE business_units SET description = %s WHERE code = %s AND org_code = %s"""
        data1 = (passed_data["description"], passed_data["code"], org_code)  
        
        cur.execute(sql1, data1)
        
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 200 status code
        return jsonify({"message": "Updated successfully", "result": "updated"}), 200
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500


# update Planner info changes
@app.route('/updateplannerinfo', methods=['PUT'])
def updateplannerinfo():
    passed_data = request.get_json()
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        org_code = passed_data.get('org_code')
        
        now = timezone2()  # Ensure this function returns the current datetime
        
        sql1 = """UPDATE planners SET name = %s, email_address = %s WHERE code = %s AND org_code = %s"""
        data1 = (passed_data["name"], passed_data["email_address"], passed_data["code"], org_code)  
        
        cur.execute(sql1, data1)
        
        conn.commit()
        
        # Close the database connection
        cur.close()
        conn.close()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Return success response with 200 status code
        return jsonify({"message": "Updated successfully", "result": "updated"}), 200
    
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500
    

#--- get user FCM token ----#
def get_fcm_token_for_user(userId, orgCode):
    try: 
        conn = dbconnect.getConnection()
        cur = conn.cursor()

        sql1 = """SELECT fcm_token FROM app_users WHERE user = %s AND org_code = %s"""
        data1 = (userId, orgCode)

        cur.execute(sql1, data1)
        result = cur.fetchone()

        cur.close()
        conn.close()

        return result[0] if result else None
    except Exception as e:
        # Log the error for debugging purposes (optional)
        print(str(e))
        return jsonify({"error": "Internal server error"}), 500


#--- get all work requests ----#
@app.route('/getworkrequests', methods=['GET'])
def getworkrequests():
    if 'email' in request.args:
        email = request.args['email']
    else:
        return "Error: No Email Address field provided. Please specify it."
    
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
        
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        if email != "":
            sql1 = """
                SELECT 
                    a.wr_id AS wr_id,
                    a.firstname AS firstname,
                    a.middlename AS middlename,
                    a.lastname AS lastname,
                    a.email_address AS email_address,
                    a.business_unit AS business_unit, 
                    e.description AS business_unit_desc, 
                    a.customer_type AS customer_type_code,
                    b.description AS customer_type, 
                    a.project_location AS project_location,
                    DATE_FORMAT(a.proposal_deadline, '%%M %%d, %%Y') AS proposal_deadline,
                    DATE_FORMAT(a.job_start_date, '%%M %%d, %%Y') AS job_start_date,
                    DATE_FORMAT(a.job_end_date, '%%M %%d, %%Y') AS job_end_date,
                    a.project_desc AS project_desc,
                    a.project_details AS project_details,
                    a.submitted_datetime AS submitted_datetime,
                    a.status AS status, 
                    a.org_code AS org_code, 
                    COUNT(d.id) AS unread_count
                FROM 
                    work_requests a
                LEFT JOIN 
                    customer_types b ON a.customer_type = b.code
                LEFT JOIN
                    business_units e ON a.business_unit = e.code 
                LEFT JOIN 
                    wr_pm_data c ON a.wr_id = c.wr_id
                LEFT JOIN 
                    app_inbox d ON c.gid = d.task_gid AND d.read_datetime IS NULL
                WHERE 
                    a.email_address = %s 
                    AND a.org_code = %s 
                GROUP BY 
                    a.wr_id, a.firstname, a.middlename, a.lastname, a.email_address, b.description, 
                    a.project_location, a.proposal_deadline, a.job_start_date, a.job_end_date, 
                    a.project_desc, a.project_details, a.submitted_datetime, a.status, a.org_code
                ORDER BY 
                    a.submitted_datetime DESC
            """
            data1 = (email, org_code)
        else:
            sql1 = """
                SELECT 
                    a.wr_id AS wr_id,
                    a.firstname AS firstname,
                    a.middlename AS middlename,
                    a.lastname AS lastname,
                    a.email_address AS email_address,
                    a.business_unit AS business_unit, 
                    e.description AS business_unit_desc, 
                    a.customer_type AS customer_type_code,
                    b.description AS customer_type, 
                    a.project_location AS project_location,
                    DATE_FORMAT(a.proposal_deadline, '%%M %%d, %%Y') AS proposal_deadline,
                    DATE_FORMAT(a.job_start_date, '%%M %%d, %%Y') AS job_start_date,
                    DATE_FORMAT(a.job_end_date, '%%M %%d, %%Y') AS job_end_date,
                    a.project_desc AS project_desc,
                    a.project_details AS project_details,
                    a.submitted_datetime AS submitted_datetime,
                    a.status AS status, 
                    a.org_code AS org_code, 
                    COUNT(d.id) AS unread_count
                FROM 
                    work_requests a
                LEFT JOIN 
                    customer_types b ON a.customer_type = b.code
                LEFT JOIN
                    business_units e ON a.business_unit = e.code 
                LEFT JOIN 
                    wr_pm_data c ON a.wr_id = c.wr_id
                LEFT JOIN 
                    app_inbox d ON c.gid = d.task_gid AND d.read_datetime IS NULL
                WHERE a.org_code = %s 
                GROUP BY 
                    a.wr_id, a.firstname, a.middlename, a.lastname, a.email_address, b.description, 
                    a.project_location, a.proposal_deadline, a.job_start_date, a.job_end_date, 
                    a.project_desc, a.project_details, a.submitted_datetime, a.status, a.org_code
                ORDER BY 
                    a.submitted_datetime DESC
            """
            data1 = (org_code)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        
        # Check if there are work requests
        if result:
            return jsonify({
                "message": "Work Requests retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No work requests found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve work requests",
            "error": str(e)
        }), 500


#--- get work requests per WR Id ----#
@app.route('/getworkrequest', methods=['GET'])
def getworkrequest():
    if 'wr_id' in request.args:
        wr_id = request.args['wr_id']
    else:
        return "Error: No WR Id field provided. Please specify it."
    
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
        
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """
                SELECT 
                    a.wr_id AS wr_id,
                    a.firstname AS firstname,
                    a.middlename AS middlename,
                    a.lastname AS lastname,
                    a.email_address AS email_address,
                    a.business_unit AS business_unit, 
                    b.description AS customer_type,
                    a.project_location AS project_location,
                    DATE_FORMAT(a.proposal_deadline, '%%M %%d, %%Y') AS proposal_deadline,
                    DATE_FORMAT(a.job_start_date, '%%M %%d, %%Y') AS job_start_date,
                    DATE_FORMAT(a.job_end_date, '%%M %%d, %%Y') AS job_end_date,
                    a.project_desc AS project_desc,
                    a.project_details AS project_details,
                    a.submitted_datetime AS submitted_datetime,
                    a.status AS status, 
                    a.org_code AS org_code 
                FROM 
                    work_requests a
                LEFT JOIN 
                    customer_types b ON a.customer_type = b.code
                LEFT JOIN 
                    wr_pm_data c ON a.wr_id = c.wr_id
                WHERE 
                    a.wr_id = %s 
                    AND a.org_code = %s 
            """
        data1 = (wr_id, org_code)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        
        # Check if there are work requests
        if result:
            return jsonify({
                "message": "Work Request retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No work request found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve work request",
            "error": str(e)
        }), 500


#--- get all customers ----#
@app.route('/getcustomers', methods=['GET'])
def getcustomers():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
        
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT id, CONCAT(firstname, ' ', middlename, ' ', lastname) AS fullname, firstname, middlename, lastname, email_address, contact_number, street_address, city, province, company_name, org_code FROM customers WHERE org_code = %s ORDER BY fullname"""
        data1 = (org_code)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        
        # Check if there are work requests
        if result:
            return jsonify({
                "message": "Customers retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No customers found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve customers",
            "error": str(e)
        }), 500


#--- get all suppliers ----#
@app.route('/getsuppliers', methods=['GET'])
def getsuppliers():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
        
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT * FROM suppliers WHERE org_code = %s ORDER BY name"""
        data1 = (org_code)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        
        # Check if there are work requests
        if result:
            return jsonify({
                "message": "Suppliers retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No suppliers found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve suppliers",
            "error": str(e)
        }), 500
        

#--- get all customer types ----#
@app.route('/getcustomertypes', methods=['GET'])
def getcustomertypes():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT * FROM customer_types WHERE status = %s AND org_code = %s"""
        data1 = (1, org_code)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "Customer Types retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No customer types found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve customer types",
            "error": str(e)
        }), 500


#--- get all item categories ----#
@app.route('/getcategories', methods=['GET'])
def getcategories():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT * FROM physical_item_categories WHERE status = %s AND org_code = %s"""
        data1 = (1, org_code)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "Categories retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No categories found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve categories",
            "error": str(e)
        }), 500
    

#--- get user to check if existing ----#
@app.route('/getuser', methods=['GET'])
def getuser():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
        
    if 'user' in request.args:
        user = request.args['user']
    else:
        return "Error: No User field provided. Please specify it."
    
    if 'login_pw' in request.args:
        login_pw = request.args['login_pw']
    else:
        return "Error: No Password provided. Please specify it."

    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT a.id AS id, a.user AS user, a.built_in AS built_in, a.built_in_password AS built_in_password, a.oauth AS oauth, a.status AS status, b.firstname AS firstname, b.middlename AS middlename, b.lastname AS lastname FROM app_users a LEFT JOIN customers b ON a.user = b.email_address WHERE a.user = %s AND a.org_code = %s AND a.status = %s"""
        data1 = (user, org_code, 1)
        
        cur.execute(sql1, data1)
        result = cur.fetchone()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        
        # Check if there are records
        if result:
            if login_pw.strip() != "":
                hashed_password = result["built_in_password"]
                is_match = verify_password(login_pw, hashed_password)  # Check password match

                if is_match:
                    return jsonify({
                        "message": "User retrieved successfully",
                        "data": result,
                        "status": "valid password"
                    }), 200
                else:
                    return jsonify({
                        "message": "Invalid password",
                        "data": result,
                        "status": "invalid password"
                    }), 401
            else:
                return jsonify({
                        "message": "User retrieved successfully",
                        "data": result,
                        "status": "valid"
                    }), 200
                    
        else:
            return jsonify({
                "message": "No user found",
                "data": [],
                "status": "no user found"
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve user",
            "data": str(e),
            "status": "error"
        }), 500
        

#--- get user roles ----#
@app.route('/getuserroles', methods=['GET'])
def getuserroles():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
        
    if 'user' in request.args:
        user = request.args['user']
    else:
        return "Error: No User field provided. Please specify it."
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT * FROM app_user_roles WHERE user = %s AND org_code = %s AND STATUS = %s"""
        data1 = (user, org_code, 1)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "User Roles retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No user roles found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve user roles",
            "error": str(e)
        }), 500


#--- get all services ----#
@app.route('/getservices', methods=['GET'])
def getservices():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
        
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor(pymysql.cursors.DictCursor)  # Use dictionary cursor
        
        sql1 = """
            SELECT 
                a.service_id,
                a.description AS service_desc,
                a.instruction AS instruction,
                JSON_ARRAYAGG(
                    JSON_OBJECT(
                        'detail_id', b.detail_id,
                        'detail_desc', b.description
                    )
                ) AS service_details
            FROM services a
            LEFT JOIN service_details b ON a.service_id = b.service_id
            WHERE a.status = %s AND a.org_code = %s 
            GROUP BY a.service_id, a.description
            ORDER BY a.sequence ASC
        """
        
        data1 = (1, org_code)
        
        cur.execute(sql1, data1)
        raw_result = cur.fetchall()  # Fetch all rows
        
        # Parse service_details JSON string into Python objects
        formatted_result = []
        for row in raw_result:
            # Convert `service_details` JSON string to a Python object
            try:
                row['service_details'] = json.loads(row['service_details'])
            except json.JSONDecodeError:
                row['service_details'] = []  # Default to empty list if parsing fails
            
            formatted_result.append(row)
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Check if there are records
        if formatted_result:
            return jsonify({
                "message": "Services retrieved successfully",
                "result": formatted_result
            }), 200
        else:
            return jsonify({
                "message": "No services found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve services",
            "error": str(e)
        }), 500


#--- get requested services per work request ----#
@app.route('/getrequestedservices', methods=['GET'])
def getrequestedservices():
    if 'wr_id' in request.args:
        wr_id = int(request.args['wr_id'])
    else:
        return "Error: No WR Id field provided. Please specify it."
    
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
        
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor(pymysql.cursors.DictCursor)  # Use dictionary cursor
        
        sql1 = """
            SELECT 
                a.service_id,
                b.description AS service_desc,
                JSON_ARRAYAGG(
                    JSON_OBJECT(
                        'detail_id', c.detail_id,
                        'detail_desc', c.description,
                        'remarks', a.remarks
                    )
                ) AS service_details
            FROM requested_services a
            LEFT JOIN services b ON a.service_id = b.service_id
            LEFT JOIN service_details c ON a.detail_id = c.detail_id
            WHERE a.wr_id = %s AND a.org_code = %s 
            GROUP BY a.service_id, b.description;
        """
        
        data1 = (wr_id, org_code)
        
        cur.execute(sql1, data1)
        raw_result = cur.fetchall()  # Fetch all rows
        
        # Parse service_details JSON string into Python objects
        formatted_result = []
        for row in raw_result:
            # Convert `service_details` JSON string to a Python object
            try:
                row['service_details'] = json.loads(row['service_details'])
            except json.JSONDecodeError:
                row['service_details'] = []  # Default to empty list if parsing fails
            
            formatted_result.append(row)
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Check if there are records
        if formatted_result:
            return jsonify({
                "message": "Requested Services retrieved successfully",
                "result": formatted_result
            }), 200
        else:
            return jsonify({
                "message": "No requested services found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve requested services",
            "error": str(e)
        }), 500


#--- get attached files per work request ----#
@app.route('/getattachments', methods=['GET'])
def getattachments():
    if 'wr_id' in request.args:
        wr_id = int(request.args['wr_id'])
    else:
        return "Error: No WR Id field provided. Please specify it."
        
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
        
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor(pymysql.cursors.DictCursor)  # Use dictionary cursor
        
        sql1 = """SELECT * FROM wr_attachments WHERE wr_id = %s AND org_code = %s"""
        
        data1 = (wr_id, org_code)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()  # Fetch all rows
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "Attachments retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No attachments found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve attachments",
            "error": str(e)
        }), 500
        

#--- get more info per work request ----#
@app.route('/getmoreinfo', methods=['GET'])
def getmoreinfo():
    if 'wr_id' in request.args:
        wr_id = int(request.args['wr_id'])
    else:
        return "Error: No WR Id field provided. Please specify it."
        
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
        
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor(pymysql.cursors.DictCursor)  # Use dictionary cursor
        
        sql1 = """
                SELECT 
                    a.wr_id AS wr_id,
                    a.firstname AS firstname,
                    a.middlename AS middlename,
                    a.lastname AS lastname,
                    a.email_address AS email_address,
                    a.business_unit AS business_unit, 
                    e.description AS business_unit_desc, 
                    a.customer_type AS customer_type_code,
                    b.description AS customer_type, 
                    a.project_location AS project_location,
                    DATE_FORMAT(a.proposal_deadline, '%%M %%d, %%Y') AS proposal_deadline,
                    DATE_FORMAT(a.job_start_date, '%%M %%d, %%Y') AS job_start_date,
                    DATE_FORMAT(a.job_end_date, '%%M %%d, %%Y') AS job_end_date,
                    a.project_desc AS project_desc,
                    a.project_details AS project_details,
                    a.submitted_datetime AS submitted_datetime,
                    a.status AS status, 
                    a.org_code AS org_code 
                FROM 
                    work_requests a
                LEFT JOIN 
                    customer_types b ON a.customer_type = b.code
                LEFT JOIN
                    business_units e ON a.business_unit = e.code 
                WHERE a.wr_id = %s AND a.org_code = %s 
            """
        
        data1 = (wr_id, org_code)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()  # Fetch all rows
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "More Info retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No more info found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve more info",
            "error": str(e)
        }), 500


#--- get messages per work request ----#
@app.route('/getmessages', methods=['GET'])
def getmessages():
    if 'wr_id' in request.args:
        wr_id = int(request.args['wr_id'])
    else:
        return "Error: No WR Id field provided. Please specify it."
        
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
        
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor(pymysql.cursors.DictCursor)  # Use dictionary cursor
        
        sql1 = """SELECT a.task_gid AS task_gid, a.message AS message, a.created_datetime AS created_datetime, a.created_by AS created_by, a.source AS source, a.read_datetime AS read_datetime FROM app_inbox a JOIN wr_pm_data b ON a.task_gid = b.gid WHERE b.wr_id = %s AND a.org_code = %s ORDER BY created_datetime"""
        
        data1 = (wr_id, org_code)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()  # Fetch all rows
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "Messages retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No messages found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve messages",
            "error": str(e)
        }), 500


#--- get messages intended for user logged in ----#
@app.route('/getusermessages', methods=['GET'])
def getusermessages():
    if 'user_login' in request.args:
        user_login = request.args['user_login']
    else:
        return "Error: No User Login field provided. Please specify it."
        
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
        
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor(pymysql.cursors.DictCursor)  # Use dictionary cursor
        
        sql1 = """SELECT title, message, created_datetime, created_by, source, action_url, status, priority, read_datetime FROM app_inbox WHERE recipient = %s AND org_code = %s ORDER BY created_datetime DESC"""
        
        data1 = (user_login, org_code)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()  # Fetch all rows
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "Messages retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No messages found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve messages",
            "error": str(e)
        }), 500


#--- get unread messages count intended for user logged in ----#
@app.route('/getuserunreadscount', methods=['GET'])
def getuserunreadscount():
    if 'user_login' in request.args:
        user_login = request.args['user_login']
    else:
        return "Error: No User Login field provided. Please specify it."
        
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
        
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor(pymysql.cursors.DictCursor)  # Use dictionary cursor
        
        sql1 = """SELECT count(*) AS count FROM app_inbox WHERE recipient = %s AND org_code = %s AND status = %s"""
        
        data1 = (user_login, org_code, "unread")
        
        cur.execute(sql1, data1)
        result = cur.fetchall()  # Fetch all rows
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "Unreads Count retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No unreads count",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve unreads count",
            "error": str(e)
        }), 500
    

#--- get all business units ----#
@app.route('/getbusinessunits', methods=['GET'])
def getbusinessunits():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT * FROM business_units WHERE status = %s AND org_code = %s"""
        data1 = (1, org_code)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "Business Units retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No business units found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve business units",
            "error": str(e)
        }), 500


#--- get all physical cu categories ----#
@app.route('/getphysicalcucategories', methods=['GET'])
def getphysicalcucategories():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT * FROM physical_cu_categories WHERE status = %s AND org_code = %s"""
        data1 = (1, org_code)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "CU Categories retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No CU Categories found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve CU Categories",
            "error": str(e)
        }), 500


#--- get all labor cu categories ----#
@app.route('/getlaborcucategories', methods=['GET'])
def getlaborcucategories():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT * FROM human_cu_categories WHERE status = %s AND org_code = %s"""
        data1 = (1, org_code)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "CU Categories retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No CU Categories found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve CU Categories",
            "error": str(e)
        }), 500


#--- get all equipment cu categories ----#
@app.route('/getequipmentcucategories', methods=['GET'])
def getequipmentcucategories():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT * FROM equip_cu_categories WHERE status = %s AND org_code = %s"""
        data1 = (1, org_code)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "CU Categories retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No CU Categories found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve CU Categories",
            "error": str(e)
        }), 500
    

#--- get all physical item categories ----#
@app.route('/getphysicalitemcategories', methods=['GET'])
def getphysicalitemcategories():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT * FROM physical_item_categories WHERE status = %s AND org_code = %s"""
        data1 = (1, org_code)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "Item Categories retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No Item Categories found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve Item Categories",
            "error": str(e)
        }), 500


#--- get all labor categories ----#
@app.route('/getlaborcategories', methods=['GET'])
def getlaborcategories():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT * FROM human_item_categories WHERE status = %s AND org_code = %s"""
        data1 = (1, org_code)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "Labor Categories retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No Labor Categories found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve Labor Categories",
            "error": str(e)
        }), 500


#--- get all equipment categories ----#
@app.route('/getequipmentcategories', methods=['GET'])
def getequipmentcategories():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT * FROM equip_item_categories WHERE status = %s AND org_code = %s"""
        data1 = (1, org_code)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "Equipment Categories retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No Equipment Categories found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve Equipment Categories",
            "error": str(e)
        }), 500
        
        
#--- get all human cu categories ----#
@app.route('/gethumancucategories', methods=['GET'])
def gethumancucategories():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT * FROM human_cu_categories WHERE status = %s AND org_code = %s"""
        data1 = (1, org_code)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "CU Categories retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No CU Categories found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve CU Categories",
            "error": str(e)
        }), 500


#--- get all equipment cu categories ----#
@app.route('/getequipcucategories', methods=['GET'])
def getequipcucategories():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT * FROM equip_cu_categories WHERE status = %s AND org_code = %s"""
        data1 = (1, org_code)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "CU Categories retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No CU Categories found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve CU Categories",
            "error": str(e)
        }), 500
        

#--- get all work request statuses ----#
@app.route('/getwrstatuses', methods=['GET'])
def getwrstatuses():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT * FROM work_request_statuses WHERE status = %s AND org_code = %s ORDER BY sequence"""
        data1 = (1, org_code)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "Work Request Statuses retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No work request statuses found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve work request statuses",
            "error": str(e)
        }), 500


#--- get all work orders statuses ----#
@app.route('/getwostatuses', methods=['GET'])
def getwostatuses():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT DISTINCT status FROM work_orders WHERE org_code = %s ORDER BY status"""
        data1 = (org_code)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "Work Order Statuses retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No work order statuses found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve work order statuses",
            "error": str(e)
        }), 500
        

#--- get all priority levels ----#
@app.route('/getprioritylevels', methods=['GET'])
def getprioritylevels():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT * FROM priority_levels WHERE status = %s AND org_code = %s ORDER BY sequence"""
        data1 = (1, org_code)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "Priority Levels retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No priority levels found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve priority levels",
            "error": str(e)
        }), 500


#--- get all planners ----#
@app.route('/getplanners', methods=['GET'])
def getplanners():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT * FROM planners WHERE status = %s AND org_code = %s ORDER BY name"""
        data1 = (1, org_code)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "Planners retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No planners found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve planners",
            "error": str(e)
        }), 500


#--- get all work orders ----#
@app.route('/getworkorders', methods=['GET'])
def getworkorders():
    if 'status' in request.args:
        status = request.args['status']
    else:
        return "Error: No Status field provided. Please specify it."
    
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
        
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        if status != "":
            sql1 = """
                SELECT 
                    a.wo_number AS wo_number,
                    a.wo_description AS wo_description, 
                    a.job_start_date AS wo_job_start_date, 
                    a.job_end_date AS wo_job_end_date, 
                    a.status AS wo_status, 
                    a.business_unit AS business_unit, 
                    e.description AS wo_priority_level, 
                    e.code AS wo_priority_level_code, 
                    a.created_datetime AS wo_created_datetime, 
                    a.due_date AS wo_due_date, 
                    a.revenue AS revenue, 
                    a.actual_total_cost AS actual_total_cost, 
                    a.gross_profit AS gross_profit, 
                    a.cost_type_used AS cost_type_used, 
                    d.name AS wo_planner, 
                    d.code AS wo_planner_code, 
                    a.location As wo_location, 
                    a.project_name AS project_name, 
                    a.project_description AS project_description, 
                    a.project_gid AS wo_project_gid, 
                    a.wr_id AS wr_id, 
                    a.org_code AS org_code, 
                    b.firstname AS firstname,
                    b.middlename AS middlename,
                    b.lastname AS lastname,
                    b.email_address AS email_address,
                    b.project_location AS project_location,
                    DATE_FORMAT(b.proposal_deadline, '%%M %%d, %%Y') AS proposal_deadline,
                    DATE_FORMAT(b.job_start_date, '%%M %%d, %%Y') AS job_start_date,
                    DATE_FORMAT(b.job_end_date, '%%M %%d, %%Y') AS job_end_date,
                    b.project_desc AS project_desc,
                    b.project_details AS project_details,
                    c.description AS customer_type 
                FROM 
                    work_orders a 
                LEFT JOIN
                    work_requests b 
                ON 
                    a.wr_id = b.wr_id
                LEFT JOIN 
                    customer_types c  
                ON 
                    b.customer_type = c.code
                LEFT JOIN 
                    planners d 
                ON 
                    a.planner = d.code 
                LEFT JOIN 
                    priority_levels e 
                ON 
                    a.priority_level = e.code 
                WHERE 
                    a.status = %s 
                AND 
                    a.org_code = %s 
                ORDER BY 
                    a.created_datetime DESC
                """

            data1 = (status, org_code)
        else:
            sql1 = """
                SELECT 
                    a.wo_number AS wo_number,
                    a.wo_description AS wo_description, 
                    a.job_start_date AS wo_job_start_date, 
                    a.job_end_date AS wo_job_end_date, 
                    a.status AS wo_status, 
                    a.business_unit AS business_unit, 
                    e.description AS wo_priority_level, 
                    e.code AS wo_priority_level_code, 
                    a.created_datetime AS wo_created_datetime, 
                    a.due_date AS wo_due_date, 
                    a.revenue AS revenue, 
                    a.actual_total_cost AS actual_total_cost, 
                    a.gross_profit AS gross_profit, 
                    a.cost_type_used AS cost_type_used, 
                    d.name AS wo_planner, 
                    d.code AS wo_planner_code, 
                    a.location As wo_location, 
                    a.project_name AS project_name, 
                    a.project_description AS project_description, 
                    a.project_gid AS wo_project_gid, 
                    a.wr_id AS wr_id, 
                    a.org_code AS org_code, 
                    b.firstname AS firstname,
                    b.middlename AS middlename,
                    b.lastname AS lastname,
                    b.email_address AS email_address,
                    b.project_location AS project_location,
                    DATE_FORMAT(b.proposal_deadline, '%%M %%d, %%Y') AS proposal_deadline,
                    DATE_FORMAT(b.job_start_date, '%%M %%d, %%Y') AS job_start_date,
                    DATE_FORMAT(b.job_end_date, '%%M %%d, %%Y') AS job_end_date,
                    b.project_desc AS project_desc,
                    b.project_details AS project_details,
                    c.description AS customer_type 
                FROM 
                    work_orders a 
                LEFT JOIN
                    work_requests b 
                ON 
                    a.wr_id = b.wr_id
                LEFT JOIN 
                    customer_types c  
                ON 
                    b.customer_type = c.code
                LEFT JOIN 
                    planners d 
                ON 
                    a.planner = d.code 
                LEFT JOIN 
                    priority_levels e 
                ON 
                    a.priority_level = e.code 
                WHERE 
                    a.org_code = %s 
                ORDER BY 
                    a.created_datetime DESC
                """

            data1 = (org_code)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        
        # Check if there are work requests
        if result:
            return jsonify({
                "message": "Work Orders retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No work orders found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve work orders",
            "error": str(e)
        }), 500


#--- get work order info ----#
@app.route('/getworkorderinfo', methods=['GET'])
def getworkorderinfo():
    if 'wo_number' in request.args:
        wo_number = int(request.args['wo_number'])
    else:
        return "Error: No Work Order Number field provided. Please specify it."
    
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
        
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """
                SELECT 
                    a.wo_number AS wo_number,
                    a.wo_description AS wo_description, 
                    a.job_start_date AS wo_job_start_date, 
                    a.job_end_date AS wo_job_end_date, 
                    a.status AS wo_status, 
                    a.business_unit AS business_unit, 
                    e.description AS wo_priority_level, 
                    e.code AS wo_priority_level_code, 
                    a.created_datetime AS wo_created_datetime, 
                    a.due_date AS wo_due_date, 
                    a.revenue AS revenue, 
                    a.actual_total_cost AS actual_total_cost, 
                    a.gross_profit AS gross_profit, 
                    a.cost_type_used AS cost_type_used, 
                    d.name AS wo_planner, 
                    d.code AS wo_planner_code, 
                    a.location As wo_location, 
                    a.project_name AS project_name, 
                    a.project_description AS project_description, 
                    a.project_gid AS wo_project_gid, 
                    a.wr_id AS wr_id, 
                    a.org_code AS org_code, 
                    b.firstname AS firstname,
                    b.middlename AS middlename,
                    b.lastname AS lastname,
                    b.email_address AS email_address,
                    b.project_location AS project_location,
                    DATE_FORMAT(b.proposal_deadline, '%%M %%d, %%Y') AS proposal_deadline,
                    DATE_FORMAT(b.job_start_date, '%%M %%d, %%Y') AS job_start_date,
                    DATE_FORMAT(b.job_end_date, '%%M %%d, %%Y') AS job_end_date,
                    b.project_desc AS project_desc,
                    b.project_details AS project_details,
                    c.description AS customer_type 
                FROM 
                    work_orders a 
                LEFT JOIN
                    work_requests b 
                ON 
                    a.wr_id = b.wr_id
                LEFT JOIN 
                    customer_types c  
                ON 
                    b.customer_type = c.code
                LEFT JOIN 
                    planners d 
                ON 
                    a.planner = d.code 
                LEFT JOIN 
                    priority_levels e 
                ON 
                    a.priority_level = e.code 
                WHERE 
                    a.wo_number = %s 
                AND 
                    a.org_code = %s 
                ORDER BY 
                    a.created_datetime DESC
                """

        data1 = (wo_number, org_code)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        
        # Check if there are work requests
        if result:
            return jsonify({
                "message": "Work Order retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No work order found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve work order",
            "error": str(e)
        }), 500
    

#--- get all standalone designs ----#
@app.route('/getstandalones', methods=['GET'])
def getstandalones():
    if 'status' in request.args:
        status = request.args['status']
    else:
        return "Error: No Status field provided. Please specify it."
    
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
        
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """
                SELECT 
                    a.sa_number AS sa_number,
                    a.sa_description AS sa_description, 
                    a.status AS sa_status, 
                    a.created_datetime AS sa_created_datetime, 
                    b.name AS sa_planner, 
                    b.code AS sa_planner_code, 
                    a.project_name AS project_name, 
                    a.project_description AS project_description, 
                    a.project_gid AS sa_project_gid, 
                    a.org_code AS org_code 
                FROM 
                    standalone_designs a 
                LEFT JOIN 
                    planners b 
                ON 
                    a.planner = b.code 
                WHERE 
                    a.status = %s AND a.org_code = %s 
                ORDER BY 
                    a.created_datetime DESC
                """

        data1 = (status, org_code)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        
        # Check if there are work requests
        if result:
            return jsonify({
                "message": "Standalone Designs retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No standalone designs found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve standalone designs",
            "error": str(e)
        }), 500
        

#--- get all physical compatible units ----#
@app.route('/getphysicalcus', methods=['GET'])
def getphysical_cus():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT a.code AS code, a.title AS title, a.description AS description, a.quantity AS quantity, a.type AS type, a.org_code AS org_code, b.category AS category_code, b.title AS category_title FROM physical_compatible_units a LEFT JOIN physical_cu_categories b ON a.category = b.category WHERE a.status = %s AND a.org_code = %s ORDER BY title"""
        data1 = (1, org_code)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "Compatible Units retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No compatible units found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve compatible units",
            "error": str(e)
        }), 500


#--- get all human compatible units ----#
@app.route('/gethumancus', methods=['GET'])
def gethuman_cus():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT a.code AS code, a.title AS title, a.description AS description, a.quantity AS quantity, a.type AS type, a.org_code AS org_code, b.category AS category_code, b.title AS category_title FROM human_compatible_units a LEFT JOIN human_cu_categories b ON a.category = b.category WHERE a.status = %s AND a.org_code = %s ORDER BY title"""
        data1 = (1, org_code)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "Compatible Units retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No compatible units found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve compatible units",
            "error": str(e)
        }), 500
        

#--- get all equipment compatible units ----#
@app.route('/getequipmentcus', methods=['GET'])
def getequipment_cus():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT a.code AS code, a.title AS title, a.description AS description, a.quantity AS quantity, a.type AS type, a.org_code AS org_code, b.category AS category_code, b.title AS category_title FROM physical_equip_compatible_units a LEFT JOIN equip_cu_categories b ON a.category = b.category WHERE a.status = %s AND a.org_code = %s ORDER BY title"""
        data1 = (1, org_code)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "Compatible Units retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No compatible units found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve compatible units",
            "error": str(e)
        }), 500
        

#--- get all selected/saved physical compatible units ----#
@app.route('/getselectedcus', methods=['GET'])
def getselected_cus():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    if 'wo_number' in request.args:
        wo_number = request.args['wo_number']
    else:
        return "Error: No WO Number field provided. Please specify it."
        
    if 'task_number' in request.args:
        task_number = request.args['task_number']
    else:
        return "Error: No Task Number field provided. Please specify it."
        
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT a.wo_number AS wo_number, a.task_number AS task_number, b.code AS code, b.category AS category_code, b.title AS title, b.description AS description, b.type AS type, a.quantity AS quantity, a.org_code AS org_code FROM wo_compatible_units a LEFT JOIN physical_compatible_units b ON a.cu_code = b.code WHERE a.wo_number = %s AND a.task_number = %s AND a.org_code = %s ORDER BY title"""
            
        data1 = (wo_number, task_number, org_code)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "Compatible Units retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No compatible units found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve compatible units",
            "error": str(e)
        }), 500


#--- get all selected/saved physical compatible units for standalone ----#
@app.route('/getselectedcus2', methods=['GET'])
def getselected_cus2():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    if 'wo_number' in request.args:
        wo_number = request.args['wo_number']
    else:
        return "Error: No WO Number field provided. Please specify it."
        
    if 'task_number' in request.args:
        task_number = request.args['task_number']
    else:
        return "Error: No Task Number field provided. Please specify it."
        
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT a.wo_number AS wo_number, a.task_number AS task_number, b.code AS code, b.title AS title, b.description AS description, b.type AS type, a.quantity AS quantity, a.org_code AS org_code FROM sa_compatible_units a LEFT JOIN physical_compatible_units b ON a.cu_code = b.code WHERE a.wo_number = %s AND a.task_number = %s AND a.org_code = %s ORDER BY title"""
            
        data1 = (wo_number, task_number, org_code)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "Compatible Units retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No compatible units found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve compatible units",
            "error": str(e)
        }), 500
        

#--- get all selected/saved human compatible units ----#
@app.route('/getselectedhumancus', methods=['GET'])
def getselected_humancus():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    if 'wo_number' in request.args:
        wo_number = request.args['wo_number']
    else:
        return "Error: No WO Number field provided. Please specify it."
        
    if 'task_number' in request.args:
        task_number = request.args['task_number']
    else:
        return "Error: No Task Number field provided. Please specify it."
        
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT a.wo_number AS wo_number, a.task_number AS task_number, b.code AS code, b.category AS category_code, b.title AS title, b.description AS description, b.type AS type, a.quantity AS quantity, a.org_code AS org_code FROM wo_human_compatible_units a LEFT JOIN human_compatible_units b ON a.cu_code = b.code WHERE a.wo_number = %s AND a.task_number = %s AND a.org_code = %s ORDER BY title"""
        data1 = (wo_number, task_number, org_code)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "Compatible Units retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No compatible units found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve compatible units",
            "error": str(e)
        }), 500


#--- get all selected/saved human compatible units for standalone ----#
@app.route('/getselectedhumancus2', methods=['GET'])
def getselected_humancus2():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    if 'wo_number' in request.args:
        wo_number = request.args['wo_number']
    else:
        return "Error: No WO Number field provided. Please specify it."
        
    if 'task_number' in request.args:
        task_number = request.args['task_number']
    else:
        return "Error: No Task Number field provided. Please specify it."
        
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT a.wo_number AS wo_number, a.task_number AS task_number, b.code AS code, b.title AS title, b.description AS description, b.type AS type, a.quantity AS quantity, a.org_code AS org_code FROM sa_human_compatible_units a LEFT JOIN human_compatible_units b ON a.cu_code = b.code WHERE a.wo_number = %s AND a.task_number = %s AND a.org_code = %s ORDER BY title"""
        data1 = (wo_number, task_number, org_code)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "Compatible Units retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No compatible units found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve compatible units",
            "error": str(e)
        }), 500
        

#--- get all selected/saved equipment compatible units ----#
@app.route('/getselectedequipcus', methods=['GET'])
def getselected_equipcus():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    if 'wo_number' in request.args:
        wo_number = request.args['wo_number']
    else:
        return "Error: No WO Number field provided. Please specify it."
        
    if 'task_number' in request.args:
        task_number = request.args['task_number']
    else:
        return "Error: No Task Number field provided. Please specify it."
        
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT a.wo_number AS wo_number, a.task_number AS task_number, b.code AS code, b.category AS category_code, b.title AS title, b.description AS description, b.type AS type, a.quantity AS quantity, a.org_code AS org_code FROM wo_equip_compatible_units a LEFT JOIN physical_equip_compatible_units b ON a.cu_code = b.code WHERE a.wo_number = %s AND a.task_number = %s AND a.org_code = %s ORDER BY title"""
        data1 = (wo_number, task_number, org_code)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "Compatible Units retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No compatible units found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve compatible units",
            "error": str(e)
        }), 500


#--- get all selected/saved equipment compatible units ----#
@app.route('/getselectedequipcus2', methods=['GET'])
def getselected_equipcus2():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    if 'wo_number' in request.args:
        wo_number = request.args['wo_number']
    else:
        return "Error: No WO Number field provided. Please specify it."
        
    if 'task_number' in request.args:
        task_number = request.args['task_number']
    else:
        return "Error: No Task Number field provided. Please specify it."
        
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT a.wo_number AS wo_number, a.task_number AS task_number, b.code AS code, b.title AS title, b.description AS description, b.type AS type, a.quantity AS quantity, a.org_code AS org_code FROM sa_equip_compatible_units a LEFT JOIN physical_equip_compatible_units b ON a.cu_code = b.code WHERE a.wo_number = %s AND a.task_number = %s AND a.org_code = %s ORDER BY title"""
        data1 = (wo_number, task_number, org_code)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "Compatible Units retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No compatible units found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve compatible units",
            "error": str(e)
        }), 500


#--- get all materials of a compatible unit ----#
@app.route('/getcumaterials', methods=['GET'])
def getcumaterials():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    if 'cu_code' in request.args:
        cu_code = request.args['cu_code']
    else:
        return "Error: No CU Code field provided. Please specify it."
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT a.cu_code AS cu_code, a.quantity AS quantity, a.quantity AS default_qty, a.unit_of_measure AS uom, b.item_code AS item_code, b.description AS item_description, b.unit_cost AS unit_cost, b.unit_cost_low AS unit_cost_low, b.unit_cost_avg AS unit_cost_avg, b.acquisition_type AS acquisition_type, a.org_code AS org_code FROM physical_cu_items a LEFT JOIN physical_items b ON a.item_code = b.item_code WHERE a.status = %s AND a.org_code = %s AND a.cu_code = %s ORDER BY item_description"""
        data1 = (1, org_code, cu_code)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "CU Materials retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No CU Materials found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve CU materials",
            "error": str(e)
        }), 500
        

#--- get all labor items of a compatible unit ----#
@app.route('/gethumanculabors', methods=['GET'])
def gethumanculabors():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    if 'cu_code' in request.args:
        cu_code = request.args['cu_code']
    else:
        return "Error: No CU Code field provided. Please specify it."
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT a.cu_code AS cu_code, a.quantity AS quantity, a.quantity AS default_qty, a.unit_of_measure AS uom, b.item_code AS item_code, b.description AS item_description, b.unit_cost AS unit_cost, b.unit_cost_low AS unit_cost_low, b.unit_cost_avg AS unit_cost_avg,b.acquisition_type AS acquisition_type, a.org_code AS org_code FROM human_cu_items a LEFT JOIN human_items b ON a.item_code = b.item_code WHERE a.status = %s AND a.org_code = %s AND a.cu_code = %s ORDER BY item_description"""
        data1 = (1, org_code, cu_code)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "CU Labor Items retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No CU Labor Items found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve CU labor items",
            "error": str(e)
        }), 500


#--- get all equipment items of a physical compatible unit ----#
@app.route('/getequipmentcuitems', methods=['GET'])
def getequipmentcuitems():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    if 'cu_code' in request.args:
        cu_code = request.args['cu_code']
    else:
        return "Error: No CU Code field provided. Please specify it."
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT a.cu_code AS cu_code, a.quantity AS quantity, a.quantity AS default_qty, a.unit_of_measure AS uom, b.item_code AS item_code, b.description AS item_description, b.unit_cost AS unit_cost, b.unit_cost_low AS unit_cost_low, b.unit_cost_avg AS unit_cost_avg,b.acquisition_type AS acquisition_type, a.org_code AS org_code FROM physical_equip_cu_items a LEFT JOIN physical_equip_items b ON a.item_code = b.item_code WHERE a.status = %s AND a.org_code = %s AND a.cu_code = %s ORDER BY item_description"""
        data1 = (1, org_code, cu_code)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "CU Equipment Items retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No CU Equipment Items found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve CU Equipment items",
            "error": str(e)
        }), 500
        

#--- get all saved materials of a physical compatible units ----#
@app.route('/getselectedcumaterials', methods=['GET'])
def getselectedcumaterials():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    if 'wo_number' in request.args:
        wo_number = request.args['wo_number']
    else:
        return "Error: No WO Number field provided. Please specify it."
    
    if 'task_number' in request.args:
        task_number = request.args['task_number']
    else:
        return "Error: No Task Number field provided. Please specify it."
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT a.cu_code AS cu_code, a.quantity AS quantity, c.quantity AS default_qty, a.uom AS uom, b.item_code AS item_code, b.description AS item_description, a.unit_cost AS unit_cost, a.unit_cost_low AS unit_cost_low, a.unit_cost_avg AS unit_cost_avg, b.acquisition_type AS acquisition_type, a.org_code AS org_code FROM wo_task_physical_items a LEFT JOIN physical_items b ON a.item_code = b.item_code LEFT JOIN physical_cu_items c ON a.cu_code = c.cu_code AND a.item_code = c.item_code WHERE a.org_code = %s AND a.wo_number = %s AND a.task_number = %s ORDER BY item_description"""
        data1 = (org_code, wo_number, task_number)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "CU Materials retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No CU Materials found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve CU materials",
            "error": str(e)
        }), 500


#--- get all saved materials of a physical compatible units for standalone ----#
@app.route('/getselectedcumaterials2', methods=['GET'])
def getselectedcumaterials2():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    if 'wo_number' in request.args:
        wo_number = request.args['wo_number']
    else:
        return "Error: No WO Number field provided. Please specify it."
    
    if 'task_number' in request.args:
        task_number = request.args['task_number']
    else:
        return "Error: No Task Number field provided. Please specify it."
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT a.cu_code AS cu_code, a.quantity AS quantity, c.quantity AS default_qty, a.uom AS uom, b.item_code AS item_code, b.description AS item_description, a.unit_cost AS unit_cost, b.acquisition_type AS acquisition_type, a.org_code AS org_code FROM sa_task_physical_items a LEFT JOIN physical_items b ON a.item_code = b.item_code LEFT JOIN physical_cu_items c ON a.cu_code = c.cu_code AND a.item_code = c.item_code WHERE a.org_code = %s AND a.wo_number = %s AND a.task_number = %s ORDER BY item_description"""
        data1 = (org_code, wo_number, task_number)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "CU Materials retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No CU Materials found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve CU materials",
            "error": str(e)
        }), 500
        

#--- get all saved labor items of a human compatible units ----#
@app.route('/getselectedhumanculabors', methods=['GET'])
def getselectedhumanculabors():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    if 'wo_number' in request.args:
        wo_number = request.args['wo_number']
    else:
        return "Error: No WO Number field provided. Please specify it."
    
    if 'task_number' in request.args:
        task_number = request.args['task_number']
    else:
        return "Error: No Task Number field provided. Please specify it."
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT a.cu_code AS cu_code, a.quantity AS quantity, c.quantity AS default_qty, a.uom AS uom, b.item_code AS item_code, b.description AS item_description, a.unit_cost AS unit_cost, b.acquisition_type AS acquisition_type, a.org_code AS org_code FROM wo_task_human_items a LEFT JOIN human_items b ON a.item_code = b.item_code LEFT JOIN human_cu_items c ON a.cu_code = c.cu_code AND a.item_code = c.item_code WHERE a.org_code = %s AND a.wo_number = %s AND a.task_number = %s ORDER BY item_description"""
        data1 = (org_code, wo_number, task_number)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "CU Labor Items retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No CU Labor Items found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve CU labor items",
            "error": str(e)
        }), 500
        

#--- get all saved labor items of a human compatible units for standalone ----#
@app.route('/getselectedhumanculabors2', methods=['GET'])
def getselectedhumanculabors2():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    if 'wo_number' in request.args:
        wo_number = request.args['wo_number']
    else:
        return "Error: No WO Number field provided. Please specify it."
    
    if 'task_number' in request.args:
        task_number = request.args['task_number']
    else:
        return "Error: No Task Number field provided. Please specify it."
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT a.cu_code AS cu_code, a.quantity AS quantity, c.quantity AS default_qty, a.uom AS uom, b.item_code AS item_code, b.description AS item_description, a.unit_cost AS unit_cost, b.acquisition_type AS acquisition_type, a.org_code AS org_code FROM sa_task_human_items a LEFT JOIN human_items b ON a.item_code = b.item_code LEFT JOIN human_cu_items c ON a.cu_code = c.cu_code AND a.item_code = c.item_code WHERE a.org_code = %s AND a.wo_number = %s AND a.task_number = %s ORDER BY item_description"""
        data1 = (org_code, wo_number, task_number)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "CU Labor Items retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No CU Labor Items found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve CU labor items",
            "error": str(e)
        }), 500
        

#--- get all saved labor items of a equipment compatible units ----#
@app.route('/getselectedequipcuitems', methods=['GET'])
def getselectedequipcuitems():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    if 'wo_number' in request.args:
        wo_number = request.args['wo_number']
    else:
        return "Error: No WO Number field provided. Please specify it."
    
    if 'task_number' in request.args:
        task_number = request.args['task_number']
    else:
        return "Error: No Task Number field provided. Please specify it."
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT a.cu_code AS cu_code, a.quantity AS quantity, c.quantity AS default_qty, a.uom AS uom, b.item_code AS item_code, b.description AS item_description, a.unit_cost AS unit_cost, b.acquisition_type AS acquisition_type, a.org_code AS org_code FROM wo_task_physical_equip_items a LEFT JOIN physical_equip_items b ON a.item_code = b.item_code LEFT JOIN physical_equip_cu_items c ON a.cu_code = c.cu_code AND a.item_code = c.item_code WHERE a.org_code = %s AND a.wo_number = %s AND a.task_number = %s ORDER BY item_description"""
        data1 = (org_code, wo_number, task_number)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "CU Equipment Items retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No CU Equipment Items found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve CU equipment items",
            "error": str(e)
        }), 500


#--- get all saved labor items of a equipment compatible units for standalone ----#
@app.route('/getselectedequipcuitems2', methods=['GET'])
def getselectedequipcuitems2():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    if 'wo_number' in request.args:
        wo_number = request.args['wo_number']
    else:
        return "Error: No WO Number field provided. Please specify it."
    
    if 'task_number' in request.args:
        task_number = request.args['task_number']
    else:
        return "Error: No Task Number field provided. Please specify it."
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT a.cu_code AS cu_code, a.quantity AS quantity, c.quantity AS default_qty, a.uom AS uom, b.item_code AS item_code, b.description AS item_description, a.unit_cost AS unit_cost, b.acquisition_type AS acquisition_type, a.org_code AS org_code FROM sa_task_physical_equip_items a LEFT JOIN physical_equip_items b ON a.item_code = b.item_code LEFT JOIN physical_equip_cu_items c ON a.cu_code = c.cu_code AND a.item_code = c.item_code WHERE a.org_code = %s AND a.wo_number = %s AND a.task_number = %s ORDER BY item_description"""
        data1 = (org_code, wo_number, task_number)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "CU Equipment Items retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No CU Equipment Items found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve CU equipment items",
            "error": str(e)
        }), 500
        

#--- get all materials ----#
@app.route('/getmaterials', methods=['GET'])
def getmaterials():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    if 'offset' in request.args:
        offset = int(request.args['offset'])
    else:
        return "Error: No Pagination Offset field provided. Please specify it."    
        
    if 'limit' in request.args:
        limit = int(request.args['limit'])
    else:
        return "Error: No Pagination Limit field provided. Please specify it."
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT a.item_code AS item_code, a.description AS description, a.unit_cost AS unit_cost, a.unit_cost_low AS unit_cost_low, a.unit_cost_avg AS unit_cost_avg, a.acquisition_type AS acquisition_type, a.unit_of_measure AS uom, a.org_code AS org_code, a.category AS category, b.description AS category_desc FROM physical_items a LEFT JOIN physical_item_categories b ON a.category = b.id WHERE a.status = %s AND a.org_code = %s ORDER BY description LIMIT %s, %s"""
        
        data1 = (1, org_code, offset, limit)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "Materials retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No Materials found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve materials",
            "error": str(e)
        }), 500


# --- get materials by partial description --- #
@app.route('/getmaterialsdesc', methods=['GET'])
def getmaterialsdesc():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    if 'description' in request.args:
        description = '%' + request.args['description'].strip() + '%'
    else:
        return "Error: No Description field provided. Please specify it."    
        
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT a.item_code AS item_code, a.description AS description, a.unit_cost AS unit_cost, a.unit_cost_low AS unit_cost_low, a.unit_cost_avg AS unit_cost_avg, a.acquisition_type AS acquisition_type, a.unit_of_measure AS uom, a.org_code AS org_code, a.category AS category, b.description AS category_desc FROM physical_items a LEFT JOIN physical_item_categories b ON a.category = b.id WHERE a.status = %s AND a.org_code = %s AND a.description LIKE %s ORDER BY description"""
        
        data1 = (1, org_code, description)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "Materials retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No Materials found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve materials",
            "error": str(e)
        }), 500
    
 
#--- get all materials per category ----#
@app.route('/getmaterialspercategory', methods=['GET'])
def getmaterialspercategory():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
        
    if 'category' in request.args:
        category = request.args['category']
    else:
        return "Error: No Category Code field provided. Please specify it."
    
    '''
    if 'offset' in request.args:
        offset = int(request.args['offset'])
    else:
        return "Error: No Pagination Offset field provided. Please specify it."    
        
    if 'limit' in request.args:
        limit = int(request.args['limit'])
    else:
        return "Error: No Pagination Limit field provided. Please specify it."
    '''
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT item_code, description, unit_cost, acquisition_type, unit_of_measure AS uom, category, org_code FROM physical_items WHERE status = %s AND org_code = %s AND category = %s ORDER BY description"""
        data1 = (1, org_code, category)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "Materials retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No Materials found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve materials",
            "error": str(e)
        }), 500


#--- get all labor per category ----#
@app.route('/getlaborpercategory', methods=['GET'])
def getlaborpercategory():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
        
    if 'category' in request.args:
        category = request.args['category']
    else:
        return "Error: No Category Code field provided. Please specify it."
    
    '''
    if 'offset' in request.args:
        offset = int(request.args['offset'])
    else:
        return "Error: No Pagination Offset field provided. Please specify it."    
        
    if 'limit' in request.args:
        limit = int(request.args['limit'])
    else:
        return "Error: No Pagination Limit field provided. Please specify it."
    '''
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT item_code, description, unit_cost, acquisition_type, unit_of_measure AS uom, category, org_code FROM human_items WHERE status = %s AND org_code = %s AND category = %s ORDER BY description"""
        data1 = (1, org_code, category)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "Labor Items retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No Labor Items found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve labor items",
            "error": str(e)
        }), 500
        
 
 #--- get all equipment per category ----#
@app.route('/getequipmentpercategory', methods=['GET'])
def getequipmentpercategory():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
        
    if 'category' in request.args:
        category = request.args['category']
    else:
        return "Error: No Category Code field provided. Please specify it."
    
    '''
    if 'offset' in request.args:
        offset = int(request.args['offset'])
    else:
        return "Error: No Pagination Offset field provided. Please specify it."    
        
    if 'limit' in request.args:
        limit = int(request.args['limit'])
    else:
        return "Error: No Pagination Limit field provided. Please specify it."
    '''
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT item_code, description, unit_cost, acquisition_type, unit_of_measure AS uom, category, org_code FROM physical_equip_items WHERE status = %s AND org_code = %s AND category = %s ORDER BY description"""
        data1 = (1, org_code, category)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "Equipment Items retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No Equipment Items found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve equipment items",
            "error": str(e)
        }), 500
 
 
#--- get all labor items ----#
@app.route('/getlabors', methods=['GET'])
def getlabors():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    if 'offset' in request.args:
        offset = int(request.args['offset'])
    else:
        return "Error: No Pagination Offset field provided. Please specify it."    
        
    if 'limit' in request.args:
        limit = int(request.args['limit'])
    else:
        return "Error: No Pagination Limit field provided. Please specify it."
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT a.item_code AS item_code, a.description AS description, a.unit_cost AS unit_cost, a.unit_cost_low AS unit_cost_low, a.unit_cost_avg AS unit_cost_avg, a.acquisition_type AS acquisition_type, a.unit_of_measure AS uom, a.org_code AS org_code, a.category AS category, b.description AS category_desc FROM human_items a LEFT JOIN human_item_categories b ON a.category = b.id WHERE a.status = %s AND a.org_code = %s ORDER BY description LIMIT %s, %s"""

        data1 = (1, org_code, offset, limit)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "Labor Items retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No Labor Items found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve labor items",
            "error": str(e)
        }), 500
 

#--- get labor items by description ----#
@app.route('/getlaborsdesc', methods=['GET'])
def getlaborsdesc():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    if 'description' in request.args:
        description = '%' + request.args['description'].strip() + '%'
    else:
        return "Error: No Description field provided. Please specify it."    
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT a.item_code AS item_code, a.description AS description, a.unit_cost AS unit_cost, a.unit_cost_low AS unit_cost_low, a.unit_cost_avg AS unit_cost_avg, a.acquisition_type AS acquisition_type, a.unit_of_measure AS uom, a.org_code AS org_code, a.category AS category, b.description AS category_desc FROM human_items a LEFT JOIN human_item_categories b ON a.category = b.id WHERE a.status = %s AND a.org_code = %s AND a.description LIKE %s ORDER BY description"""

        data1 = (1, org_code, description)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "Labor Items retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No Labor Items found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve labor items",
            "error": str(e)
        }), 500


#--- get equipment items by description ----#
@app.route('/getequipmentitemsdesc', methods=['GET'])
def getequipmentitemsdesc():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    if 'description' in request.args:
        description = '%' + request.args['description'].strip() + '%'
    else:
        return "Error: No Description field provided. Please specify it."    
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT a.item_code AS item_code, a.description AS description, a.unit_cost AS unit_cost, a.unit_cost_low AS unit_cost_low, a.unit_cost_avg AS unit_cost_avg, a.acquisition_type AS acquisition_type, a.unit_of_measure AS uom, a.org_code AS org_code, a.category AS category, b.description AS category_desc FROM physical_equip_items a LEFT JOIN equip_item_categories b ON a.category = b.id WHERE a.status = %s AND a.org_code = %s AND a.description LIKE %s ORDER BY description"""
        
        data1 = (1, org_code, description)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "Equipment Items retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No Equipment Items found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve equipment items",
            "error": str(e)
        }), 500
    
 
#--- get all equipment items ----#
@app.route('/getequipmentitems', methods=['GET'])
def getequipmentitems():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    if 'offset' in request.args:
        offset = int(request.args['offset'])
    else:
        return "Error: No Pagination Offset field provided. Please specify it."    
        
    if 'limit' in request.args:
        limit = int(request.args['limit'])
    else:
        return "Error: No Pagination Limit field provided. Please specify it."
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT a.item_code AS item_code, a.description AS description, a.unit_cost AS unit_cost, a.unit_cost_low AS unit_cost_low, a.unit_cost_avg AS unit_cost_avg, a.acquisition_type AS acquisition_type, a.unit_of_measure AS uom, a.org_code AS org_code, a.category AS category, b.description AS category_desc FROM physical_equip_items a LEFT JOIN equip_item_categories b ON a.category = b.id WHERE a.status = %s AND a.org_code = %s ORDER BY description LIMIT %s, %s"""
        
        data1 = (1, org_code, offset, limit)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "Equipment Items retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No Equipment Items found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve equipment items",
            "error": str(e)
        }), 500
       

#--- get all material CUs ----#
@app.route('/getmaterialcus', methods=['GET'])
def getmaterialcus():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    if 'offset' in request.args:
        offset = int(request.args['offset'])
    else:
        return "Error: No Pagination Offset field provided. Please specify it."    
        
    if 'limit' in request.args:
        limit = int(request.args['limit'])
    else:
        return "Error: No Pagination Limit field provided. Please specify it."
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT a.code AS code, a.title AS title, a.description AS description, a.quantity AS quantity, a.type AS type, a.category AS category, b.title AS category_title  FROM physical_compatible_units a LEFT JOIN physical_cu_categories b ON a.category = b.category WHERE a.status = %s AND a.org_code = %s ORDER BY title LIMIT %s, %s"""
        
        data1 = (1, org_code, offset, limit)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "CUs retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No CUs found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve CUs",
            "error": str(e)
        }), 500 


#--- get all labor CUs ----#
@app.route('/getlaborcus', methods=['GET'])
def getlaborcus():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    if 'offset' in request.args:
        offset = int(request.args['offset'])
    else:
        return "Error: No Pagination Offset field provided. Please specify it."    
        
    if 'limit' in request.args:
        limit = int(request.args['limit'])
    else:
        return "Error: No Pagination Limit field provided. Please specify it."
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT a.code AS code, a.title AS title, a.description AS description, a.quantity AS quantity, a.type AS type, a.category AS category, b.title AS category_title  FROM human_compatible_units a LEFT JOIN human_cu_categories b ON a.category = b.category WHERE a.status = %s AND a.org_code = %s ORDER BY title LIMIT %s, %s"""
        
        data1 = (1, org_code, offset, limit)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "CUs retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No CUs found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve CUs",
            "error": str(e)
        }), 500 


#--- get all saved custom materials ----#
@app.route('/getselectedcustommaterials', methods=['GET'])
def getselectedcustommaterials():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    if 'wo_number' in request.args:
        wo_number = request.args['wo_number']
    else:
        return "Error: No WO Number field provided. Please specify it."    
        
    if 'task_number' in request.args:
        task_number = request.args['task_number']
    else:
        return "Error: No Task Number field provided. Please specify it."
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT a.item_code AS item_code, b.description AS description, a.quantity AS quantity, a.uom AS uom, a.unit_cost AS unit_cost, a.unit_cost_low AS unit_cost_low, a.unit_cost_avg AS unit_cost_avg, a.total_cost AS total_cost, a.total_cost_low AS total_cost_low, a.total_cost_avg AS total_cost_avg, b.acquisition_type AS acquisition_type, a.org_code AS org_code FROM wo_task_physical_custom_items a LEFT JOIN physical_items b ON a.item_code = b.item_code WHERE a.org_code = %s AND a.wo_number = %s AND a.task_number = %s ORDER BY description"""
        data1 = (org_code, wo_number, task_number)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "Materials retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No Materials found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve materials",
            "error": str(e)
        }), 500


#--- get all saved custom materials for standalone ----#
@app.route('/getselectedcustommaterials2', methods=['GET'])
def getselectedcustommaterials2():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    if 'wo_number' in request.args:
        wo_number = request.args['wo_number']
    else:
        return "Error: No WO Number field provided. Please specify it."    
        
    if 'task_number' in request.args:
        task_number = request.args['task_number']
    else:
        return "Error: No Task Number field provided. Please specify it."
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT a.item_code AS item_code, b.description AS description, a.quantity AS quantity, a.uom AS uom, a.unit_cost AS unit_cost, a.total_cost AS total_cost, b.acquisition_type AS acquisition_type, a.org_code AS org_code FROM sa_task_physical_custom_items a LEFT JOIN physical_items b ON a.item_code = b.item_code WHERE a.org_code = %s AND a.wo_number = %s AND a.task_number = %s ORDER BY description"""
        data1 = (org_code, wo_number, task_number)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "Materials retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No Materials found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve materials",
            "error": str(e)
        }), 500
        

#--- get all saved custom labor items ----#
@app.route('/getselectedhumancustomlabors', methods=['GET'])
def getselectedhumancustomlabors():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    if 'wo_number' in request.args:
        wo_number = request.args['wo_number']
    else:
        return "Error: No WO Number field provided. Please specify it."    
        
    if 'task_number' in request.args:
        task_number = request.args['task_number']
    else:
        return "Error: No Task Number field provided. Please specify it."
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT a.item_code AS item_code, b.description AS description, a.quantity AS quantity, a.uom AS uom, a.unit_cost AS unit_cost, a.total_cost AS total_cost, b.acquisition_type AS acquisition_type, a.org_code AS org_code FROM wo_task_human_custom_items a LEFT JOIN human_items b ON a.item_code = b.item_code WHERE a.org_code = %s AND a.wo_number = %s AND a.task_number = %s ORDER BY description"""
        data1 = (org_code, wo_number, task_number)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "Labor Items retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No Labor Items found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve labor items",
            "error": str(e)
        }), 500        
        

#--- get all saved custom labor items ----#
@app.route('/getselectedhumancustomlabors2', methods=['GET'])
def getselectedhumancustomlabors2():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    if 'wo_number' in request.args:
        wo_number = request.args['wo_number']
    else:
        return "Error: No WO Number field provided. Please specify it."    
        
    if 'task_number' in request.args:
        task_number = request.args['task_number']
    else:
        return "Error: No Task Number field provided. Please specify it."
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT a.item_code AS item_code, b.description AS description, a.quantity AS quantity, a.uom AS uom, a.unit_cost AS unit_cost, a.total_cost AS total_cost, b.acquisition_type AS acquisition_type, a.org_code AS org_code FROM sa_task_human_custom_items a LEFT JOIN human_items b ON a.item_code = b.item_code WHERE a.org_code = %s AND a.wo_number = %s AND a.task_number = %s ORDER BY description"""
        data1 = (org_code, wo_number, task_number)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "Labor Items retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No Labor Items found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve labor items",
            "error": str(e)
        }), 500        


#--- get all saved custom equipment items ----#
@app.route('/getselectedequipcustomitems', methods=['GET'])
def getselectedequipcustomitems():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    if 'wo_number' in request.args:
        wo_number = request.args['wo_number']
    else:
        return "Error: No WO Number field provided. Please specify it."    
        
    if 'task_number' in request.args:
        task_number = request.args['task_number']
    else:
        return "Error: No Task Number field provided. Please specify it."
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT a.item_code AS item_code, b.description AS description, a.quantity AS quantity, a.uom AS uom, a.unit_cost AS unit_cost, a.total_cost AS total_cost, b.acquisition_type AS acquisition_type, a.org_code AS org_code FROM wo_task_physical_equip_custom_items a LEFT JOIN physical_equip_items b ON a.item_code = b.item_code WHERE a.org_code = %s AND a.wo_number = %s AND a.task_number = %s ORDER BY description"""
        data1 = (org_code, wo_number, task_number)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "Equipment Items retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No Equipment Items found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve equipment items",
            "error": str(e)
        }), 500
        

#--- get all saved custom equipment items for standalone ----#
@app.route('/getselectedequipcustomitems2', methods=['GET'])
def getselectedequipcustomitems2():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    if 'wo_number' in request.args:
        wo_number = request.args['wo_number']
    else:
        return "Error: No WO Number field provided. Please specify it."    
        
    if 'task_number' in request.args:
        task_number = request.args['task_number']
    else:
        return "Error: No Task Number field provided. Please specify it."
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT a.item_code AS item_code, b.description AS description, a.quantity AS quantity, a.uom AS uom, a.unit_cost AS unit_cost, a.total_cost AS total_cost, b.acquisition_type AS acquisition_type, a.org_code AS org_code FROM sa_task_physical_equip_custom_items a LEFT JOIN physical_equip_items b ON a.item_code = b.item_code WHERE a.org_code = %s AND a.wo_number = %s AND a.task_number = %s ORDER BY description"""
        data1 = (org_code, wo_number, task_number)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "Equipment Items retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No Equipment Items found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve equipment items",
            "error": str(e)
        }), 500
        
   
#--- get bill of materials ----        
@app.route('/getbommaterials', methods=['GET'])
def get_bom_materials():
    if 'wo_number' in request.args:
        wo_number = int(request.args['wo_number'])
    else:
        return "Error: No WO Number field provided. Please specify it."
        
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    try:
        conn = dbconnect.getConnection()
        curs = conn.cursor()
        
        # SQL Query to retrieve compatible units and custom resources
        query = """
        SELECT 
            'Compatible Unit' AS type, 
            c.title AS cu_title, 
            a.item_code AS item_code, 
            b.description AS description, 
            a.quantity AS quantity, 
            a.unit_cost AS unit_cost, 
            a.unit_cost_low AS unit_cost_low, 
            a.unit_cost_avg AS unit_cost_avg, 
            (a.quantity * a.unit_cost) AS total_cost, 
            (a.quantity * a.unit_cost_low) AS total_cost_low, 
            (a.quantity * a.unit_cost_avg) AS total_cost_avg, 
            a.uom AS uom 
        FROM 
            wo_task_physical_items a 
        LEFT JOIN 
            physical_items b 
        ON 
            a.item_code = b.item_code 
        LEFT JOIN 
            physical_compatible_units c 
        ON 
            a.cu_code = c.code 
        WHERE 
            a.wo_number = %s 

        UNION ALL

        SELECT 
            'Custom Resource' AS type,
            'Custom' AS cu_title, 
            a.item_code AS item_code, 
            b.description AS description, 
            a.quantity AS quantity, 
            a.unit_cost AS unit_cost, 
            a.unit_cost_low AS unit_cost_low, 
            a.unit_cost_avg AS unit_cost_avg, 
            (a.quantity * a.unit_cost) AS total_cost, 
            (a.quantity * a.unit_cost_low) AS total_cost_low, 
            (a.quantity * a.unit_cost_avg) AS total_cost_avg, 
            a.uom AS uom 
        FROM 
            wo_task_physical_custom_items a 
        LEFT JOIN
            physical_items b 
        ON
            a.item_code = b.item_code 
        WHERE 
            a.wo_number = %s
        """
        
        # Execute query
        curs.execute(query, (wo_number, wo_number))
        materials = curs.fetchall()

        # Group materials by type (Compatible Unit or Custom Resource)
        grouped_materials = {
            "Compatible Unit": {},
            "Custom Resource": {}
        }

        for material in materials:
            material_type = material['type']
            cu_title = material['cu_title']
            item_data = {
                'item_code': material['item_code'],
                'description': material['description'],
                'quantity': material['quantity'],
                'unit_cost': material['unit_cost'],
                'unit_cost_low': material['unit_cost_low'],
                'unit_cost_avg': material['unit_cost_avg'],
                'total_cost': material['total_cost'],
                'total_cost_low': material['total_cost_low'],
                'total_cost_avg': material['total_cost_avg'],
                'uom': material['uom']
            }

            # Group by type, then by cu_title
            if cu_title not in grouped_materials[material_type]:
                grouped_materials[material_type][cu_title] = []
            grouped_materials[material_type][cu_title].append(item_data)

        # Prepare the response
        result = {
            'wo_number': wo_number,
            'materials': []
        }

        # Add the grouped data to the response
        for material_type, cu_data in grouped_materials.items():
            type_group = {'type': material_type, 'cu_groups': []}
            for cu_title, items in cu_data.items():
                type_group['cu_groups'].append({
                    'cu_title': cu_title,
                    'items': items
                })
            result['materials'].append(type_group)

        # Check if there are records
        if result['materials']:
            return jsonify({
                "message": "Materials retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No Materials found",
                "result": []
            }), 404

    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve materials",
            "error": str(e)
        }), 500


#--- get bill of materials for standalone ----        
@app.route('/getbommaterials2', methods=['GET'])
def get_bom_materials2():
    if 'wo_number' in request.args:
        wo_number = int(request.args['wo_number'])
    else:
        return "Error: No WO Number field provided. Please specify it."
        
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    try:
        conn = dbconnect.getConnection()
        curs = conn.cursor()
        
        # SQL Query to retrieve compatible units and custom resources
        query = """
        SELECT 
            'Compatible Unit' AS type, 
            c.title AS cu_title, 
            a.item_code AS item_code, 
            b.description AS description, 
            a.quantity AS quantity, 
            a.unit_cost AS unit_cost, 
            (a.quantity * a.unit_cost) AS total_cost, 
            a.uom AS uom 
        FROM 
            sa_task_physical_items a 
        LEFT JOIN 
            physical_items b 
        ON 
            a.item_code = b.item_code 
        LEFT JOIN 
            physical_compatible_units c 
        ON 
            a.cu_code = c.code 
        WHERE 
            a.wo_number = %s 

        UNION ALL

        SELECT 
            'Custom Resource' AS type,
            'Custom' AS cu_title, 
            a.item_code AS item_code, 
            b.description AS description, 
            a.quantity AS quantity, 
            a.unit_cost AS unit_cost, 
            (a.quantity * a.unit_cost) AS total_cost, 
            a.uom AS uom 
        FROM 
            sa_task_physical_custom_items a 
        LEFT JOIN
            physical_items b 
        ON
            a.item_code = b.item_code 
        WHERE 
            a.wo_number = %s
        """
        
        # Execute query
        curs.execute(query, (wo_number, wo_number))
        materials = curs.fetchall()

        # Group materials by type (Compatible Unit or Custom Resource)
        grouped_materials = {
            "Compatible Unit": {},
            "Custom Resource": {}
        }

        for material in materials:
            material_type = material['type']
            cu_title = material['cu_title']
            item_data = {
                'item_code': material['item_code'],
                'description': material['description'],
                'quantity': material['quantity'],
                'unit_cost': material['unit_cost'],
                'total_cost': material['total_cost'],
                'uom': material['uom']
            }

            # Group by type, then by cu_title
            if cu_title not in grouped_materials[material_type]:
                grouped_materials[material_type][cu_title] = []
            grouped_materials[material_type][cu_title].append(item_data)

        # Prepare the response
        result = {
            'wo_number': wo_number,
            'materials': []
        }

        # Add the grouped data to the response
        for material_type, cu_data in grouped_materials.items():
            type_group = {'type': material_type, 'cu_groups': []}
            for cu_title, items in cu_data.items():
                type_group['cu_groups'].append({
                    'cu_title': cu_title,
                    'items': items
                })
            result['materials'].append(type_group)

        # Check if there are records
        if result['materials']:
            return jsonify({
                "message": "Materials retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No Materials found",
                "result": []
            }), 404

    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve materials",
            "error": str(e)
        }), 500
        

#--- get BoM - labor ----        
@app.route('/getbomlabor', methods=['GET'])
def get_bom_labor():
    if 'wo_number' in request.args:
        wo_number = int(request.args['wo_number'])
    else:
        return "Error: No WO Number field provided. Please specify it."
        
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    try:
        conn = dbconnect.getConnection()
        curs = conn.cursor()
        
        # SQL Query to retrieve compatible units and custom resources
        query = """
        SELECT 
            'Compatible Unit' AS type, 
            c.title AS cu_title, 
            a.item_code AS item_code, 
            b.description AS description, 
            a.quantity AS quantity, 
            a.unit_cost AS unit_cost, 
            (a.quantity * a.unit_cost) AS total_cost, 
            a.uom AS uom 
        FROM 
            wo_task_human_items a 
        LEFT JOIN 
            human_items b 
        ON 
            a.item_code = b.item_code 
        LEFT JOIN 
            human_compatible_units c 
        ON 
            a.cu_code = c.code 
        WHERE 
            a.wo_number = %s 

        UNION ALL

        SELECT 
            'Custom Resource' AS type,
            'Custom' AS cu_title, 
            a.item_code AS item_code, 
            b.description AS description, 
            a.quantity AS quantity, 
            a.unit_cost AS unit_cost, 
            (a.quantity * a.unit_cost) AS total_cost, 
            a.uom AS uom 
        FROM 
            wo_task_human_custom_items a 
        LEFT JOIN
            human_items b 
        ON
            a.item_code = b.item_code 
        WHERE 
            a.wo_number = %s
        """
        
        # Execute query
        curs.execute(query, (wo_number, wo_number))
        materials = curs.fetchall()

        # Group materials by type (Compatible Unit or Custom Resource)
        grouped_materials = {
            "Compatible Unit": {},
            "Custom Resource": {}
        }

        for material in materials:
            material_type = material['type']
            cu_title = material['cu_title']
            item_data = {
                'item_code': material['item_code'],
                'description': material['description'],
                'quantity': material['quantity'],
                'unit_cost': material['unit_cost'],
                'total_cost': material['total_cost'],
                'uom': material['uom']
            }

            # Group by type, then by cu_title
            if cu_title not in grouped_materials[material_type]:
                grouped_materials[material_type][cu_title] = []
            grouped_materials[material_type][cu_title].append(item_data)

        # Prepare the response
        result = {
            'wo_number': wo_number,
            'materials': []
        }

        # Add the grouped data to the response
        for material_type, cu_data in grouped_materials.items():
            type_group = {'type': material_type, 'cu_groups': []}
            for cu_title, items in cu_data.items():
                type_group['cu_groups'].append({
                    'cu_title': cu_title,
                    'items': items
                })
            result['materials'].append(type_group)

        # Check if there are records
        if result['materials']:
            return jsonify({
                "message": "Materials retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No Materials found",
                "result": []
            }), 404

    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve materials",
            "error": str(e)
        }), 500


#--- get BoM - labor for standalone ----        
@app.route('/getbomlabor2', methods=['GET'])
def get_bom_labor2():
    if 'wo_number' in request.args:
        wo_number = int(request.args['wo_number'])
    else:
        return "Error: No WO Number field provided. Please specify it."
        
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    try:
        conn = dbconnect.getConnection()
        curs = conn.cursor()
        
        # SQL Query to retrieve compatible units and custom resources
        query = """
        SELECT 
            'Compatible Unit' AS type, 
            c.title AS cu_title, 
            a.item_code AS item_code, 
            b.description AS description, 
            a.quantity AS quantity, 
            a.unit_cost AS unit_cost, 
            (a.quantity * a.unit_cost) AS total_cost, 
            a.uom AS uom 
        FROM 
            sa_task_human_items a 
        LEFT JOIN 
            human_items b 
        ON 
            a.item_code = b.item_code 
        LEFT JOIN 
            human_compatible_units c 
        ON 
            a.cu_code = c.code 
        WHERE 
            a.wo_number = %s 

        UNION ALL

        SELECT 
            'Custom Resource' AS type,
            'Custom' AS cu_title, 
            a.item_code AS item_code, 
            b.description AS description, 
            a.quantity AS quantity, 
            a.unit_cost AS unit_cost, 
            (a.quantity * a.unit_cost) AS total_cost, 
            a.uom AS uom 
        FROM 
            sa_task_human_custom_items a 
        LEFT JOIN
            human_items b 
        ON
            a.item_code = b.item_code 
        WHERE 
            a.wo_number = %s
        """
        
        # Execute query
        curs.execute(query, (wo_number, wo_number))
        materials = curs.fetchall()

        # Group materials by type (Compatible Unit or Custom Resource)
        grouped_materials = {
            "Compatible Unit": {},
            "Custom Resource": {}
        }

        for material in materials:
            material_type = material['type']
            cu_title = material['cu_title']
            item_data = {
                'item_code': material['item_code'],
                'description': material['description'],
                'quantity': material['quantity'],
                'unit_cost': material['unit_cost'],
                'total_cost': material['total_cost'],
                'uom': material['uom']
            }

            # Group by type, then by cu_title
            if cu_title not in grouped_materials[material_type]:
                grouped_materials[material_type][cu_title] = []
            grouped_materials[material_type][cu_title].append(item_data)

        # Prepare the response
        result = {
            'wo_number': wo_number,
            'materials': []
        }

        # Add the grouped data to the response
        for material_type, cu_data in grouped_materials.items():
            type_group = {'type': material_type, 'cu_groups': []}
            for cu_title, items in cu_data.items():
                type_group['cu_groups'].append({
                    'cu_title': cu_title,
                    'items': items
                })
            result['materials'].append(type_group)

        # Check if there are records
        if result['materials']:
            return jsonify({
                "message": "Materials retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No Materials found",
                "result": []
            }), 404

    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve materials",
            "error": str(e)
        }), 500
        

#--- get BoM - Equipment ----        
@app.route('/getbomequipment', methods=['GET'])
def get_bom_equipment():
    if 'wo_number' in request.args:
        wo_number = int(request.args['wo_number'])
    else:
        return "Error: No WO Number field provided. Please specify it."
        
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    try:
        conn = dbconnect.getConnection()
        curs = conn.cursor()
        
        # SQL Query to retrieve compatible units and custom resources
        query = """
        SELECT 
            'Compatible Unit' AS type, 
            c.title AS cu_title, 
            a.item_code AS item_code, 
            b.description AS description, 
            a.quantity AS quantity, 
            a.unit_cost AS unit_cost, 
            (a.quantity * a.unit_cost) AS total_cost, 
            a.uom AS uom 
        FROM 
            wo_task_physical_equip_items a 
        LEFT JOIN 
            physical_equip_items b 
        ON 
            a.item_code = b.item_code 
        LEFT JOIN 
            physical_equip_compatible_units c 
        ON 
            a.cu_code = c.code 
        WHERE 
            a.wo_number = %s 

        UNION ALL

        SELECT 
            'Custom Resource' AS type,
            'Custom' AS cu_title, 
            a.item_code AS item_code, 
            b.description AS description, 
            a.quantity AS quantity, 
            a.unit_cost AS unit_cost, 
            (a.quantity * a.unit_cost) AS total_cost, 
            a.uom AS uom 
        FROM 
            wo_task_physical_equip_custom_items a 
        LEFT JOIN
            physical_equip_items b 
        ON
            a.item_code = b.item_code 
        WHERE 
            a.wo_number = %s
        """
        
        # Execute query
        curs.execute(query, (wo_number, wo_number))
        materials = curs.fetchall()

        # Group materials by type (Compatible Unit or Custom Resource)
        grouped_materials = {
            "Compatible Unit": {},
            "Custom Resource": {}
        }

        for material in materials:
            material_type = material['type']
            cu_title = material['cu_title']
            item_data = {
                'item_code': material['item_code'],
                'description': material['description'],
                'quantity': material['quantity'],
                'unit_cost': material['unit_cost'],
                'total_cost': material['total_cost'],
                'uom': material['uom']
            }

            # Group by type, then by cu_title
            if cu_title not in grouped_materials[material_type]:
                grouped_materials[material_type][cu_title] = []
            grouped_materials[material_type][cu_title].append(item_data)

        # Prepare the response
        result = {
            'wo_number': wo_number,
            'materials': []
        }

        # Add the grouped data to the response
        for material_type, cu_data in grouped_materials.items():
            type_group = {'type': material_type, 'cu_groups': []}
            for cu_title, items in cu_data.items():
                type_group['cu_groups'].append({
                    'cu_title': cu_title,
                    'items': items
                })
            result['materials'].append(type_group)

        # Check if there are records
        if result['materials']:
            return jsonify({
                "message": "Materials retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No Materials found",
                "result": []
            }), 404

    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve materials",
            "error": str(e)
        }), 500


#--- get BoM - Equipment for standalone ----        
@app.route('/getbomequipment2', methods=['GET'])
def get_bom_equipment2():
    if 'wo_number' in request.args:
        wo_number = int(request.args['wo_number'])
    else:
        return "Error: No WO Number field provided. Please specify it."
        
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    try:
        conn = dbconnect.getConnection()
        curs = conn.cursor()
        
        # SQL Query to retrieve compatible units and custom resources
        query = """
        SELECT 
            'Compatible Unit' AS type, 
            c.title AS cu_title, 
            a.item_code AS item_code, 
            b.description AS description, 
            a.quantity AS quantity, 
            a.unit_cost AS unit_cost, 
            (a.quantity * a.unit_cost) AS total_cost, 
            a.uom AS uom 
        FROM 
            sa_task_physical_equip_items a 
        LEFT JOIN 
            physical_equip_items b 
        ON 
            a.item_code = b.item_code 
        LEFT JOIN 
            physical_equip_compatible_units c 
        ON 
            a.cu_code = c.code 
        WHERE 
            a.wo_number = %s 

        UNION ALL

        SELECT 
            'Custom Resource' AS type,
            'Custom' AS cu_title, 
            a.item_code AS item_code, 
            b.description AS description, 
            a.quantity AS quantity, 
            a.unit_cost AS unit_cost, 
            (a.quantity * a.unit_cost) AS total_cost, 
            a.uom AS uom 
        FROM 
            sa_task_physical_equip_custom_items a 
        LEFT JOIN
            physical_equip_items b 
        ON
            a.item_code = b.item_code 
        WHERE 
            a.wo_number = %s
        """
        
        # Execute query
        curs.execute(query, (wo_number, wo_number))
        materials = curs.fetchall()

        # Group materials by type (Compatible Unit or Custom Resource)
        grouped_materials = {
            "Compatible Unit": {},
            "Custom Resource": {}
        }

        for material in materials:
            material_type = material['type']
            cu_title = material['cu_title']
            item_data = {
                'item_code': material['item_code'],
                'description': material['description'],
                'quantity': material['quantity'],
                'unit_cost': material['unit_cost'],
                'total_cost': material['total_cost'],
                'uom': material['uom']
            }

            # Group by type, then by cu_title
            if cu_title not in grouped_materials[material_type]:
                grouped_materials[material_type][cu_title] = []
            grouped_materials[material_type][cu_title].append(item_data)

        # Prepare the response
        result = {
            'wo_number': wo_number,
            'materials': []
        }

        # Add the grouped data to the response
        for material_type, cu_data in grouped_materials.items():
            type_group = {'type': material_type, 'cu_groups': []}
            for cu_title, items in cu_data.items():
                type_group['cu_groups'].append({
                    'cu_title': cu_title,
                    'items': items
                })
            result['materials'].append(type_group)

        # Check if there are records
        if result['materials']:
            return jsonify({
                "message": "Materials retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No Materials found",
                "result": []
            }), 404

    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve materials",
            "error": str(e)
        }), 500
        

#--- get work order cost estimate ----#
@app.route('/getwocostestimate', methods=['GET'])
def getwocostestimate():
    if 'wo_number' in request.args:
        wo_number = int(request.args['wo_number'])
    else:
        return "Error: No WO Number field provided. Please specify it."
        
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
        
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor(pymysql.cursors.DictCursor)  # Use dictionary cursor
        
        sql1 = """SELECT * FROM wo_cost_estimates WHERE wo_number = %s AND org_code = %s"""
        
        data1 = (wo_number, org_code)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()  # Fetch all rows
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "Cost Estimate retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No cost estimate found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve cost estimate",
            "error": str(e)
        }), 500


#--- get work order cost estimate for standalone ----#
@app.route('/getwocostestimate2', methods=['GET'])
def getwocostestimate2():
    if 'wo_number' in request.args:
        wo_number = int(request.args['wo_number'])
    else:
        return "Error: No WO Number field provided. Please specify it."
        
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
        
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor(pymysql.cursors.DictCursor)  # Use dictionary cursor
        
        sql1 = """SELECT * FROM sa_cost_estimates WHERE wo_number = %s AND org_code = %s"""
        
        data1 = (wo_number, org_code)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()  # Fetch all rows
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "Cost Estimate retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No cost estimate found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve cost estimate",
            "error": str(e)
        }), 500


#--- get work orders count ----#
@app.route('/getworkorderscount', methods=['GET'])
def getworkorderscount():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
        
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor(pymysql.cursors.DictCursor)  # Use dictionary cursor
        
        sql1 = """SELECT status, COUNT(*) AS wo_count 
                FROM work_orders 
                WHERE status IN ('New', 'Kickoff', 'Executed', 'Billed', 'Closed') 
                AND org_code = %s 
                GROUP BY status"""
        data1 = (org_code)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()  # Fetch all rows
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Process the result to map statuses to the required output format
        status_counts = { "New": 0, "Kickoff": 0, "Executed": 0, "Billed": 0, "Closed": 0 }
        
        
        # Map the results to the response format
        for row in result:
            status = row['status']
            count = row['wo_count']
            if status in status_counts:
                status_counts[status] = count
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "Work Orders Count retrieved successfully",
                "result": status_counts
            }), 200
        else:
            return jsonify({
                "message": "No count found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to count work orders",
            "error": str(e)
        }), 500


#--- get work orders count by BUs ----#
@app.route('/getworkorderscountbybu', methods=['GET'])
def getworkorderscount_by_bu():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return jsonify({
            "message": "Error: No Organization Code field provided. Please specify it."
        }), 400
        
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor(pymysql.cursors.DictCursor)  # Use dictionary cursor
        
        sql1 =  """
                SELECT business_unit, COUNT(*) AS wo_count 
                FROM work_orders 
                WHERE org_code = %s 
                GROUP BY business_unit
                """
        data1 = (org_code,)  # Ensure tuple format
        
        cur.execute(sql1, data1)
        result = cur.fetchall()  # Fetch all rows
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Process the result into a dictionary format
        bu_counts = {row['business_unit']: row['wo_count'] for row in result}

        # Check if there are records
        if result:
            return jsonify({
                "message": "Work Orders Count retrieved successfully",
                "result": bu_counts
            }), 200
        else:
            return jsonify({
                "message": "No count found",
                "result": {}
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to count work orders",
            "error": str(e)
        }), 500
        

#--- get work orders profit by BUs ----#
@app.route('/getworkordersprofitbybu', methods=['GET'])
def getworkordersprofit_by_bu():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return jsonify({
            "message": "Error: No Organization Code field provided. Please specify it."
        }), 400
        
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor(pymysql.cursors.DictCursor)  # Use dictionary cursor
        
        sql1 =  """
                SELECT business_unit, SUM(gross_profit) AS wo_profit 
                FROM work_orders 
                WHERE org_code = %s 
                GROUP BY business_unit
                """
        data1 = (org_code,)  # Ensure tuple format
        
        cur.execute(sql1, data1)
        result = cur.fetchall()  # Fetch all rows
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Process the result into a dictionary format
        bu_counts = {row['business_unit']: row['wo_profit'] for row in result}

        # Check if there are records
        if result:
            return jsonify({
                "message": "Work Orders Profit retrieved successfully",
                "result": bu_counts
            }), 200
        else:
            return jsonify({
                "message": "No profit found",
                "result": {}
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to sum profit of work orders",
            "error": str(e)
        }), 500


#--- get work requests count ----#
@app.route('/getworkrequestscount', methods=['GET'])
def getworkrequestscount():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
        
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor(pymysql.cursors.DictCursor)  # Use dictionary cursor
        
        sql1 = """SELECT status, COUNT(*) AS wr_count 
                FROM work_requests  
                WHERE status IN ('Queue', 'On Review', 'Accepted', 'Declined', 'On Hold') 
                AND org_code = %s 
                GROUP BY status"""
        data1 = (org_code)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()  # Fetch all rows
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Process the result to map statuses to the required output format
        status_counts = { "Queue": 0, "On Review": 0, "Accepted": 0, "Declined": 0, "On Hold": 0 }
        
        
        # Map the results to the response format
        for row in result:
            status = row['status']
            count = row['wr_count']
            if status in status_counts:
                status_counts[status] = count
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "Work Requests Count retrieved successfully",
                "result": status_counts
            }), 200
        else:
            return jsonify({
                "message": "No count found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to count work requests",
            "error": str(e)
        }), 500


#--- get work requests and work orders for approval ----#
@app.route('/getwrwoapproval', methods=['GET'])
def getwrwoapproval():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."

    if 'role_titles' in request.args:
        role_titles_param = request.args.get("role_titles", "")
        role_titles = role_titles_param.split(",")
    else:
        return "Error: No Role Title field provided. Please specify it."
        
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor(pymysql.cursors.DictCursor)  # Use dictionary cursor
        
        if "team lead" in role_titles and "manager" in role_titles:
            sql1 = """SELECT * FROM approval_requests WHERE (action_status IS NULL OR action_status = '') AND approval_type IN ('Pending 1st Pre-Approval', 'Pending 2nd Pre-Approval', 'Pending Approval') AND org_code = %s ORDER BY requested_datetime DESC"""
            data1 = (org_code)

        elif "team lead" in role_titles:
            sql1 = """SELECT * FROM approval_requests WHERE (action_status IS NULL OR action_status = '') AND approval_type IN ('Pending 1st Pre-Approval', 'Pending 2nd Pre-Approval') AND org_code = %s ORDER BY requested_datetime DESC"""
            data1 = (org_code)

        elif "manager" in role_titles:
            sql1 = """SELECT * FROM approval_requests WHERE (action_status IS NULL OR action_status = '') AND approval_type IN ('Pending Approval') AND org_code = %s ORDER BY requested_datetime DESC"""
            data1 = (org_code)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()  # Fetch all rows
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "WR & WO for Approval retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No WR or WO for Approval found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrive WR and WO for Approval",
            "error": str(e)
        }), 500


#--- get all work logs per user ----#
@app.route('/getworklogs', methods=['GET'])
def getworklogs():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    if 'email_address' in request.args:
        email_address = request.args['email_address']
    else:
        return "Error: No Email Address field provided. Please specify it."
        
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor(pymysql.cursors.DictCursor)  # Use dictionary cursor
        
        sql1 = """SELECT * FROM work_logs WHERE email_address = %s AND org_code = %s ORDER BY log_datetime DESC"""
        data1 = (email_address, org_code)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()  # Fetch all rows
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "Work Logs retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No Work Logs found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrive work logs",
            "error": str(e)
        }), 500


#--- get all timesheet per user ----#
@app.route('/gettimesheet', methods=['GET'])
def gettimesheet():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    if 'work_log_id' in request.args:
        work_log_id = request.args['work_log_id']
    else:
        return "Error: No Work Log Id field provided. Please specify it."
        
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor(pymysql.cursors.DictCursor)  # Use dictionary cursor
        
        sql1 = """SELECT * FROM timesheets WHERE work_log_id = %s AND org_code = %s ORDER BY start DESC"""
        data1 = (work_log_id, org_code)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()  # Fetch all rows
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "Timesheets retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No Timesheets found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrive timesheets",
            "error": str(e)
        }), 500


#--- get all asigned materials per supplier ----#
@app.route('/getassignedmaterials', methods=['GET'])
def getassignedmaterials():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    if 'supplier_id' in request.args:
        supplier_id = request.args['supplier_id']
    else:
        return "Error: No Supplier ID field provided. Please specify it."
        
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        sql1 = """SELECT a.supplier_id AS supplier_id, a.item_code AS item_code, b.description AS description FROM supplier_materials a LEFT JOIN physical_items b ON a.item_code = b.item_code WHERE a.supplier_id = %s AND a.org_code = %s ORDER by description"""
        data1 = (supplier_id, org_code)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        
        # Check if there are work requests
        if result:
            return jsonify({
                "message": "Materials Assigned retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No materials found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve materials",
            "error": str(e)
        }), 500


#--- get work order CU alterations per CU ----#
@app.route('/getwocu_alterations', methods=['GET'])
def getwocu_alterations():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    if 'wo_number' in request.args:
        wo_number = request.args['wo_number']
    else:
        return "Error: No WO Number field provided. Please specify it."    
        
    if 'cu_code' in request.args:
        cu_code = request.args['cu_code']
    else:
        return "Error: No CU Code field provided. Please specify it."
        
    if 'design_type' in request.args:
        design_type = request.args['design_type']
    else:
        return "Error: No Design Type field provided. Please specify it."
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        if design_type == "SA":
            sql1 = """SELECT * FROM sa_cu_alterations WHERE org_code = %s AND wo_number = %s AND cu_code = %s ORDER BY created_datetime DESC"""
        else:
            sql1 = """SELECT * FROM wo_cu_alterations WHERE org_code = %s AND wo_number = %s AND cu_code = %s ORDER BY created_datetime DESC"""
            
        data1 = (org_code, wo_number, cu_code)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "CU Alterations retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No CU Alterations found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve CU alterations",
            "error": str(e)
        }), 500


#--- get work order CU alterations ----#
@app.route('/getwocu_alterationsall', methods=['GET'])
def getwocu_alterationsall():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    if 'wo_number' in request.args:
        wo_number = request.args['wo_number']
    else:
        return "Error: No WO Number field provided. Please specify it."    
        
    if 'design_type' in request.args:
        design_type = request.args['design_type']
    else:
        return "Error: No Design Type field provided. Please specify it."
    
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        if design_type == "SA":
            sql1 = """SELECT * FROM sa_cu_alterations WHERE org_code = %s AND wo_number = %s ORDER BY created_datetime DESC"""
        else:
            sql1 = """SELECT * FROM wo_cu_alterations WHERE org_code = %s AND wo_number = %s ORDER BY created_datetime DESC"""
            
        data1 = (org_code, wo_number)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "CU Alterations retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No CU Alterations found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve CU alterations",
            "error": str(e)
        }), 500


#--- get work order approval history ----#
@app.route('/getwoapprovalhistory', methods=['GET'])
def getwoapprovalhistory():
    if 'org_code' in request.args:
        org_code = request.args['org_code']
    else:
        return "Error: No Organization Code field provided. Please specify it."
    
    if 'wo_number' in request.args:
        wo_number = request.args['wo_number']
    else:
        return "Error: No WO Number field provided. Please specify it."    
        
    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()
        
        
        sql1 = """SELECT * FROM approval_requests WHERE org_code = %s AND txn_type = %s AND txn_reference = %s ORDER BY requested_datetime DESC"""
            
        data1 = (org_code, 'Work Order', wo_number)
        
        cur.execute(sql1, data1)
        result = cur.fetchall()
        
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        
        # Check if there are records
        if result:
            return jsonify({
                "message": "Approval History retrieved successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "message": "No Approval History found",
                "result": []
            }), 404
        
    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve Approval History",
            "error": str(e)
        }), 500


# --- Get email address to check if it exists ---
@app.route('/getemailaddress', methods=['GET'])
def getemailaddress():
    org_code = request.args.get('org_code')
    email_address = request.args.get('email_address')

    if not org_code:
        return jsonify({
            "message": "Error: No Organization Code field provided. Please specify it.",
            "result": False
        }), 400

    if not email_address:
        return jsonify({
            "message": "Error: No Email Address field provided. Please specify it.",
            "result": False
        }), 400

    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()

        sql = """SELECT 1 FROM app_users WHERE org_code = %s AND user = %s"""
        cur.execute(sql, (org_code, email_address))
        record = cur.fetchone()

        if record:
            return jsonify({
                "message": "Email Address already exists",
                "result": True
            }), 200
        else:
            return jsonify({
                "message": "Email Address not found",
                "result": False
            }), 200

    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve Email Address",
            "error": str(e),
            "result": False
        }), 500
    

# --- Get Material CU Code to check if it exists ---
@app.route('/getcucode', methods=['GET'])
def getcucode():
    org_code = request.args.get('org_code')
    cu_code = request.args.get('cu_code')

    if not org_code:
        return jsonify({
            "message": "Error: No Organization Code field provided. Please specify it.",
            "result": False
        }), 400

    if not cu_code:
        return jsonify({
            "message": "Error: No CU Code field provided. Please specify it.",
            "result": False
        }), 400

    try:
        conn = dbconnect.getConnection()
        cur = conn.cursor()

        sql = """SELECT 1 FROM physical_compatible_units WHERE org_code = %s AND code = %s"""
        cur.execute(sql, (org_code, cu_code))
        record = cur.fetchone()

        if record:
            return jsonify({
                "message": "CU Code already exists",
                "result": True
            }), 200
        else:
            return jsonify({
                "message": "CU Code not found",
                "result": False
            }), 200

    except Exception as e:
        return jsonify({
            "message": "Failed to retrieve CU Code",
            "error": str(e),
            "result": False
        }), 500
    

#-- Generate new number for material CUs, MAT series
def get_next_cu_code(series_name):
    conn = dbconnect.getConnection()
    cur = conn.cursor()
    
    # Lock the table to avoid race condition (if needed)
    cur.execute("SELECT last_number FROM cu_code_series FOR UPDATE")
    row = cur.fetchone()

    last_number = int(row['last_number'])
    next_number = last_number + 1
    
    # Update the counter
    cur.execute("UPDATE cu_code_series SET last_number = %s", (next_number,))
    conn.commit()
    conn.close()

    return f"{series_name}{str(next_number).zfill(7)}"


#-- Generate new number for cu category code
def get_next_cu_category_code():
    conn = dbconnect.getConnection()
    cur = conn.cursor()
    
    # Lock the table to avoid race condition (if needed)
    cur.execute("SELECT last_number FROM cu_category_code_series FOR UPDATE")
    row = cur.fetchone()

    last_number = int(row['last_number'])
    next_number = last_number + 1
    
    # Update the counter
    cur.execute("UPDATE cu_category_code_series SET last_number = %s", (next_number,))
    conn.commit()
    conn.close()

    return f"CAT{str(next_number).zfill(7)}"


#-- Generate new number for business unit code
def get_next_business_unit_code():
    conn = dbconnect.getConnection()
    cur = conn.cursor()
    
    # Lock the table to avoid race condition (if needed)
    cur.execute("SELECT last_number FROM business_unit_code_series FOR UPDATE")
    row = cur.fetchone()

    last_number = int(row['last_number'])
    next_number = last_number + 1
    
    # Update the counter
    cur.execute("UPDATE business_unit_code_series SET last_number = %s", (next_number,))
    conn.commit()
    conn.close()

    return f"BU{str(next_number).zfill(6)}"


# method to hash password
def hash_password(password: str) -> str:
    """Hashes the given password and returns the hashed version."""
    if not password:
        raise ValueError("Password cannot be empty")
    
    hashed_password = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    return hashed_password
 
    
# to verify password
def verify_password(login_pw: str, hashed_pw: str) -> bool:
    """Checks if the provided login password matches the hashed password."""
    return bcrypt.checkpw(login_pw.encode(), hashed_pw.encode())


'''
def hash_password(password: str) -> bytes:  # Return bytes, not string
    """Hashes the given password and returns the hashed version."""
    if not password:
        raise ValueError("Password cannot be empty")
    
    hashed_password = bcrypt.hashpw(password.encode(), bcrypt.gensalt())  
    return hashed_password  # Store this in the database as bytes

def verify_password(login_pw: str, hashed_pw: bytes) -> bool:
    """Checks if the provided login password matches the stored hash."""
    return bcrypt.checkpw(login_pw.encode(), hashed_pw)  # No need to encode hashed_pw
'''
        
if __name__ == "__main__":
    app.run(threaded=True)
    #app.run(host='0.0.0.0', port=8000)
    socketio.run(app, host='0.0.0.0', port=8001)
    
