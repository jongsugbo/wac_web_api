from flask import Flask, request, jsonify, Response
import dbconnect
import simplejson as json
from flask_cors import CORS
import urllib.request
import json
import logging
import threading
import time
import pytz
import re
from event_bus import EventBus
from handlers import handler_save_to_mysql
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests
from datetime import datetime, timedelta

# for Socket.IO
from flask_socketio import SocketIO, send

# for google FCM
from google.oauth2 import service_account
import google.auth.transport.requests

# for Pusher data stream
import pusher

# for AWS Textract and Bedrock

# for Asana
import asana

from app_routes_select import register_select_routes
from app_routes_select_02 import register_timesheets_reports_routes
from app_routes_mutate import register_mutate_routes

from config import settings

app = Flask(__name__)

# Enable CORS for all routes
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# Asana API configuration as Header
ASANA_API_TOKEN = settings.asana_api_token

HEADERS = {
    "Authorization": f"Bearer {ASANA_API_TOKEN}",
    "Content-Type": "application/json",
}

PORTFOLIO_GID = settings.asana_portfolio_gid
WORKSPACE_GID = settings.asana_workspace_gid
POLL_INTERVAL = settings.poll_interval
WEBHOOK_URL = settings.webhook_url


# Configure Pusher
pusher_client = pusher.Pusher(
  app_id=settings.pusher_app_id,
  key=settings.pusher_key,
  secret=settings.pusher_secret,
  cluster=settings.pusher_cluster,
  ssl=True
)

# Configure Asana
client = asana.Client.access_token(ASANA_API_TOKEN)

# Configure logging to write to a file
logging.basicConfig(
    level=settings.log_level,
    filename="app.log",
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Register routes
register_select_routes(app)
register_timesheets_reports_routes(app)
register_mutate_routes(app)

@app.route('/')
def home():
    #logger.info("Hello, Madayaw UAT!")
    return "Hello, WAC Dev on Flask EC2!"

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
    SERVICE_ACCOUNT_FILE = settings.firebase_service_account_file
    PROJECT_ID = settings.firebase_project_id

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
        #logger.info(f"Subscribing to project {project_gid}...")

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
            #logger.info(f"Response status: {response.status}")
            
            # Read the response body for more detailed error message
            response_body = response.read().decode("utf-8")
            #logger.info(f"Response body: {response_body}")

            if response.status == 201:
                #logger.info(f"Successfully subscribed to project {project_gid}.")
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


# Polling function for detecting new projects and changes to existing projects
def poll_portfolio():
    global previous_projects, subscribed_projects, subscribed_projects_details

    conn = dbconnect.getConnection()
    cur = conn.cursor()

    try:
        # Fetch previous projects from the database
        logger.info("Fetching previous projects from the database...")
        sql_fetch_previous = f"""SELECT project_gid FROM work_orders WHERE org_code = '{settings.org_code}'"""
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
                            data = (project_name, wr_id, timezone2(), 'New', project_gid, settings.org_code)

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

# Start polling on server startup (remarks: stopped, not needed for now)
##start_polling()


# Asana webhook handler for the subscription, getting data from Asana
@app.route('/asana-webhook-handler', methods=['POST'])
def asana_webhook_handler():
    #logger.info("asana_webhook_handler called")
    try:
        # Handle X-Hook-Secret for Asana verification
        if 'X-Hook-Secret' in request.headers:
            return '', 200, {'X-Hook-Secret': request.headers['X-Hook-Secret']}
        
        # Parse the JSON payload
        payload = request.json
        if not payload:
            return jsonify({"error": "Invalid or missing JSON payload"}), 400

        # Log the payload for debugging
        #logger.info(f"Payload received: {payload}")

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

# Fetches the project_id for a given task.
def fetch_project_id(task_id):
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


# Fetch project id from the task details with opt_fields
def fetch_task_details(task_gid):
    url = f"https://app.asana.com/api/1.0/tasks/{task_gid}?opt_fields=name,projects"
    headers = {
        "Authorization": f"Bearer {ASANA_API_TOKEN}"
    }
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        return response.json().get("data")
    else:
        logger.error(f"Failed to fetch task details: {response.text}")
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


# Handle the payload sent by Asana webhook
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
            #logger.info("Project ID: ")
            #logger.info(project_id)

            if project_id:
                # Fetch project name and description via API
                new_name, new_description = extract_project_details(project_id)
                #logger.info("Fetched project details:")
                #logger.info(f"Name: {new_name}")
                #logger.info(f"Description: {new_description}")

                if new_name or new_description:
                    #logger.info("Detected project updates.")

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
                        #logger.info(f"Project name changed from '{current_name}' to '{new_name}'")

                        sql_update_name = """
                            UPDATE work_orders 
                            SET project_name = %s
                            WHERE project_gid = %s
                        """
                        cur.execute(sql_update_name, (new_name, project_id))
                        conn.commit()

                    if new_description and new_description != current_description:
                        #logger.info(f"Project description changed from '{current_description}' to '{new_description}'")

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
                #logger.info("Task ID: ")
                #logger.info(task_gid)

                # Fetch sections dynamically for the task to check status changes
                sections = get_project_sections(project_id)
                section_id = event.get("parent", {}).get("gid")
                task_id = event.get("resource", {}).get("gid")

                #logger.info("Section Name: " + sections.get(section_id, "Unknown"))

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

                #logger.info(f"Processing comment on task {task_gid}...")

                # Fetch task details to get project_gid
                task_details = fetch_task_details(task_gid)
                project_gid = None
                task_name = None

                if task_details:
                    task_name = task_details.get("name")
                    projects = task_details.get("projects", [])
                    if projects:
                        project_gid = projects[0].get("gid")  # Take the first project if multiple

                # Fetch comment details via API
                comment_details = fetch_comment_details(comment_gid)
                if comment_details:
                    comment_text = comment_details.get("text")
                    created_at = now ##comment_details.get("created_at")
                    created_by = comment_details.get("created_by", {}).get("name")
                    #created_by = comment_details.get("created_by", {}).get("email")

                    #logger.info(f"Captured comment: {comment_text} (Created by: {created_by} at {created_at})")

                    # SQL for inserting the comment into the database
                    sql_insert_comment = """
                        INSERT INTO task_comments
                        (task_gid, comment_gid, comment_text, created_at, created_by, org_code)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """
                    cur.execute(sql_insert_comment, (task_gid, comment_gid, comment_text, created_at, created_by, settings.org_code))
                    conn.commit()
                    
                    # Check if the comment is directed to @customer, case insensitive
                    # if comment_text.strip().startswith("@customer"):
                    if comment_text.strip().lower().startswith("@1e"):
                        #logger.info(f"Comment directed to customer: {comment_text}")

                        # If there are attachment URLs, append them to the comment_text
                        #if attachments_urls:
                        #    comment_text += "\n\nAttachments:\n" + "\n".join(attachments_urls)

                        # Insert into app_chatbox table
                        sql_insert_inbox = """
                            INSERT INTO app_chatbox
                            (project_gid, task_gid, task_name, comment_gid, message, created_datetime, created_by, source, org_code)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """
                        cur.execute(sql_insert_inbox, (project_gid, task_gid, task_name, comment_gid, comment_text, created_at, created_by, 'asana', settings.org_code))
                        conn.commit()

                        pusher_client.trigger('inbox-channel', 'new-message', {'refresh': True})
                        
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
                                        SELECT a.email_address AS email_address, a.project_desc AS project_desc, a.firstname AS firstname, a.lastname AS lastname, a.wr_id AS wr_id 
                                        FROM work_requests a 
                                        WHERE a.project_gid = %s
                                        """
                        cur.execute(sql_fetch_wr, (project_gid,))
                        current_wr = cur.fetchone()
                        
                        if current_wr:
                            email_address = current_wr['email_address']
                            project_desc = current_wr['project_desc']
                            first_name = current_wr['firstname']
                            last_name = current_wr['lastname']
                            wr_id = current_wr['wr_id']
                        
                            send_email_notification(email_address, project_desc, first_name, last_name, wr_id, comment_text)
                        else:
                            logger.error("No data found for the given project_gid.")
                            email_address, project_desc, first_name, last_name, wr_id = None, None, None, None, None
                        
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
                            
        #logger.info(f"unread message count: {unread_count}")
            
    except Exception as e:
        logger.error(f"Failed to send unread messages count notification: {e}")


# fetch file attachments of a task
def fetch_attachments_for_task(task_gid):
    url = f"https://app.asana.com/api/1.0/tasks/{task_gid}/attachments"
    headers = {"Authorization": f"Bearer {ASANA_API_TOKEN}"}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json().get("data", [])
    else:
        logger.error(f"Failed to fetch attachments for task {task_gid}: {response.text}")
        return []
    

# Send email notification
def send_email_notification(email_address, project_desc, first_name, last_name, wr_id, comment):
    """Sends an email notification for the work request update."""
    try:
        sender_email = settings.gmail_sender
        receiver_email = email_address.strip()  # Strip any whitespace
        password = settings.gmail_app_password
        
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
            f"Please find below the recent comment from Vivant Asana User:\n\n"
            f"-----------------------------------\n"
            f"Comment:\n"
            f"\"{comment}\"\n"
            f"-----------------------------------\n\n"
            f"Here are the details of your work request:\n\n"
            f"Work Request Description: {project_desc}\n"
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


@app.post("/asana/upload")
def asana_upload():
    """
    Browser-safe proxy: receives multipart (task_gid, file) and forwards to Asana.
    Returns Asana's response as-is (status + body).
    """
    task_gid = request.form.get("task_gid")
    f = request.files.get("file")

    if not task_gid or not f:
        return jsonify({"error": "task_gid and file are required"}), 400

    # Stream the file straight to Asana (avoid loading into memory)
    files = {
        "file": (f.filename, f.stream, f.mimetype or "application/octet-stream")
    }
    data = {"parent": task_gid}
    headers = {"Authorization": f"Bearer {ASANA_API_TOKEN}"}

    try:
        r = requests.post(
            "https://app.asana.com/api/1.0/attachments",
            headers=headers,
            data=data,
            files=files,
            timeout=120,
        )
        # Pass Asana's response body & status straight through
        # Asana replies JSON; keep it raw so the client can read errors[].
        return Response(r.text, status=r.status_code, content_type=r.headers.get("Content-Type", "application/json"))
    except requests.RequestException as e:
        return jsonify({"error": f"Asana upload failed: {str(e)}"}), 502


# GET /asana/task/<task_gid>/attachments  → proxies Asana per-task attachments
@app.get("/asana/task/<task_gid>/attachments")
def get_task_attachments(task_gid):
    headers = {"Authorization": f"Bearer {ASANA_API_TOKEN}"}
    # Ask for useful fields; tweak as needed
    params = {
        "opt_fields": "name,download_url,permanent_url,created_at,resource_subtype,created_by.name,host"
    }
    r = requests.get(
        f"https://app.asana.com/api/1.0/tasks/{task_gid}/attachments",
        headers=headers,
        params=params,
        timeout=60,
    )
    return Response(r.text, status=r.status_code, content_type="application/json")


if __name__ == "__main__":
    app.run(threaded=True)
    #app.run(host='0.0.0.0', port=8000)
    socketio.run(app, host='0.0.0.0', port=8001)