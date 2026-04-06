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

app = Flask(__name__)
CORS(app)

PLAYBOOKS_DIR = "playbooks"
USER_DATA_FILE = "/user_data/user_data.yml"

def run_playbook(playbook_name, output_queue):
    """Execute ansible-playbook and stream output to queue"""
    playbook_path = os.path.join(PLAYBOOKS_DIR, f"{playbook_name}.yml")

    if not os.path.exists(playbook_path):
        output_queue.put(f"ERROR: Playbook {playbook_name}.yml not found\n")
        output_queue.put("__DONE__")
        return

    try:
        # Build ansible-playbook command with extra vars file
        cmd = ["ansible-playbook", playbook_path, "-v"]

        # Add user data vars file if it exists
        if os.path.exists(USER_DATA_FILE):
            cmd.extend(["-e", f"@{USER_DATA_FILE}"])

        # Set up environment for unbuffered output
        env = os.environ.copy()
        env['PYTHONUNBUFFERED'] = '1'
        env['ANSIBLE_FORCE_COLOR'] = '1'

        # Run ansible-playbook with line-buffered output
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            universal_newlines=True,
            env=env
        )

        # Stream output line by line
        for line in iter(process.stdout.readline, ''):
            if line:
                output_queue.put(line)
                # Force flush to ensure real-time streaming
                import sys
                sys.stdout.flush()

        process.wait()

        if process.returncode == 0:
            output_queue.put("\n✓ Playbook completed successfully!\n")
        else:
            output_queue.put(f"\n✗ Playbook failed with exit code {process.returncode}\n")

    except Exception as e:
        output_queue.put(f"\nERROR: {str(e)}\n")
    finally:
        output_queue.put("__DONE__")

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
