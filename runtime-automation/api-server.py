#!/usr/bin/env python3
"""
Simple API server for executing Ansible playbooks and streaming output
"""
import os
import subprocess
import json
from flask import Flask, Response, request, jsonify
from flask_cors import CORS
import threading
import queue
import time
import tempfile

app = Flask(__name__)
CORS(app)

PLAYBOOKS_DIR = "playbooks"
USER_DATA_FILE = "/user_data/user_data.yml"
LOG_DIR = "/tmp/playbook-logs"

# Ensure log directory exists
os.makedirs(LOG_DIR, exist_ok=True)

def run_playbook(playbook_name, output_queue):
    """Execute ansible-playbook and stream output to queue via tail -f"""
    playbook_path = os.path.join(PLAYBOOKS_DIR, f"{playbook_name}.yml")

    if not os.path.exists(playbook_path):
        output_queue.put(f"ERROR: Playbook {playbook_name}.yml not found\n")
        output_queue.put("__DONE__")
        return

    # Create unique log file for this execution
    log_file = os.path.join(LOG_DIR, f"{playbook_name}-{int(time.time())}.log")

    try:
        # Build ansible-playbook command with extra vars file
        # Use stdbuf to force line-buffered output for real-time streaming
        cmd = ["stdbuf", "-oL", "ansible-playbook", playbook_path, "-v"]

        # Add user data vars file if it exists
        if os.path.exists(USER_DATA_FILE):
            cmd.extend(["-e", f"@{USER_DATA_FILE}"])

        # Set up environment for unbuffered output
        env = os.environ.copy()
        env['PYTHONUNBUFFERED'] = '1'
        env['ANSIBLE_FORCE_COLOR'] = '0'  # Disable color for cleaner logs

        # Create the log file first
        open(log_file, 'w').close()

        # Start tail -f on the log file in a separate thread
        tail_process = subprocess.Popen(
            ["tail", "-f", log_file],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            universal_newlines=True
        )

        # Start the playbook execution
        with open(log_file, 'w') as log:
            playbook_process = subprocess.Popen(
                cmd,
                stdout=log,
                stderr=subprocess.STDOUT,
                env=env
            )

        # Stream output from tail and watch for Ansible completion
        playbook_complete = False
        while not playbook_complete:
            line = tail_process.stdout.readline()
            if line:
                output_queue.put(line)
                # Check for Ansible PLAY RECAP marker
                if 'PLAY RECAP' in line and '*' in line:
                    playbook_complete = True
                    # Immediately terminate tail to avoid blocking
                    tail_process.terminate()
            else:
                # If no output and process ended, break
                if playbook_process.poll() is not None:
                    break

        # Give ansible a moment to write final lines
        time.sleep(0.2)

        # Read final lines directly from the log file (not from tail)
        with open(log_file, 'r') as final_read:
            lines = final_read.readlines()
            # Send the last 5 lines (to catch the stats line after PLAY RECAP)
            for line in lines[-5:]:
                output_queue.put(line)

        # Wait for tail to finish terminating
        try:
            tail_process.wait(timeout=1)
        except:
            pass

        # Wait for playbook to complete
        playbook_process.wait()

        if playbook_process.returncode == 0:
            output_queue.put("\n✓ Playbook completed successfully!\n")
        else:
            output_queue.put(f"\n✗ Playbook failed with exit code {playbook_process.returncode}\n")

    except Exception as e:
        output_queue.put(f"\nERROR: {str(e)}\n")
    finally:
        output_queue.put("__DONE__")
        # Clean up old log files (keep last 10)
        try:
            logs = sorted([f for f in os.listdir(LOG_DIR) if f.endswith('.log')])
            if len(logs) > 10:
                for old_log in logs[:-10]:
                    os.remove(os.path.join(LOG_DIR, old_log))
        except:
            pass

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy"}), 200

@app.route('/solve/<module_name>', methods=['GET'])
def solve_module(module_name):
    """Execute solve playbook for a module and stream output"""

    def generate():
        output_queue = queue.Queue()

        # Start playbook execution in background thread
        thread = threading.Thread(
            target=run_playbook,
            args=(f"solve-{module_name}", output_queue)
        )
        thread.daemon = True
        thread.start()

        # Stream output as Server-Sent Events
        yield f"data: Starting solve playbook for {module_name}...\n\n"

        while True:
            try:
                line = output_queue.get(timeout=0.1)
                if line == "__DONE__":
                    yield f"data: __DONE__\n\n"
                    break
                # Send as SSE format
                yield f"data: {json.dumps(line)}\n\n"
            except queue.Empty:
                # Send keepalive
                yield f": keepalive\n\n"

    return Response(generate(), mimetype='text/event-stream')

@app.route('/validate/<module_name>', methods=['GET'])
def validate_module(module_name):
    """Execute validate playbook for a module and stream output"""

    def generate():
        output_queue = queue.Queue()

        # Start playbook execution in background thread
        thread = threading.Thread(
            target=run_playbook,
            args=(f"validate-{module_name}", output_queue)
        )
        thread.daemon = True
        thread.start()

        # Stream output as Server-Sent Events
        yield f"data: Starting validation playbook for {module_name}...\n\n"

        while True:
            try:
                line = output_queue.get(timeout=0.1)
                if line == "__DONE__":
                    yield f"data: __DONE__\n\n"
                    break
                # Send as SSE format
                yield f"data: {json.dumps(line)}\n\n"
            except queue.Empty:
                # Send keepalive
                yield f": keepalive\n\n"

    return Response(generate(), mimetype='text/event-stream')

@app.route('/playbooks', methods=['GET'])
def list_playbooks():
    """List available playbooks"""
    playbooks = []
    if os.path.exists(PLAYBOOKS_DIR):
        playbooks = [f for f in os.listdir(PLAYBOOKS_DIR) if f.endswith('.yml')]
    return jsonify({"playbooks": playbooks}), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)
