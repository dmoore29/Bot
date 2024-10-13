from flask import Flask, jsonify
from flask_cors import CORS
import subprocess

app = Flask(__name__)
CORS(app)  # Enable CORS

SERVICE_NAME = 'bot.service'  # Change to your service name

@app.route('/start', methods=['POST'])
def start_script():
    subprocess.call(['sudo', 'systemctl', 'start', SERVICE_NAME])
    return jsonify({"status": "Script started"}), 200

@app.route('/stop', methods=['POST'])
def stop_script():
    subprocess.call(['sudo', 'systemctl', 'stop', SERVICE_NAME])
    return jsonify({"status": "Script stopped"}), 200

@app.route('/status', methods=['GET'])
def check_status():
    result = subprocess.run(['systemctl', 'is-active', SERVICE_NAME], stdout=subprocess.PIPE)
    status = result.stdout.decode('utf-8').strip()
    return jsonify({"status": status}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
