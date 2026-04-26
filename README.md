# Project AngelWare: AI-Enhanced Search and Rescue

Project AngelWare is a hardware-software integration designed to assist firefighters in high-stakes search-and-rescue operations. By combining ESP32-based CSI (Channel State Information) sensing with AI-driven automated dispatch, AngelWare ensures victims are identified behind walls and reported to medical services in seconds.

## **The Problem**
In active fire scenarios, communication is hindered by smoke, noise, and physical exhaustion. When a firefighter discovers a victim, relaying information to medical teams via radio is often slow or impossible, delaying life-saving care.

## **The Solution**
Project AngelWare streamlines the transition from **detection to dispatch** through a silent, one-touch interface on a wearable display.

### **Core Features**
* **CSI Sensing Mesh:** Utilizes ESP32-S3 nodes to detect human presence/motion behind walls via signal disruption.
* **One-Touch Activation:** Firefighters tap the victim's location on a Freenove DSI display powered by a Raspberry Pi.
* **Silent AI Dispatch:** * **Twilio Voice API:** Automatically initiates an emergency call to hospitals.
    * **ElevenLabs Conversational AI:** Converts LLM-generated situational reports (SITREPs) into natural, high-clarity speech for the receiver.
* **Edge-to-Cloud Inference:** Real-time camera capture processed via OpenCV and streamed over WebSockets to a RunPod GPU instance running **DensePose** for advanced pose estimation.

---

## **Tech Stack**

### **Languages**
* **Python:** Backend logic, AI integration, and UI.
* **C:** ESP32-S3 mesh node firmware.
* **PowerShell:** Deployment and environment orchestration.

### **Frameworks & Libraries**
* **UI/Frontend:** Pygame
* **Computer Vision:** OpenCV (Capture, JPEG encode/decode), Detectron2 + DensePose
* **Machine Learning:** PyTorch, NumPy
* **Communication:** WebSockets (Real-time streaming), PySerial (Hardware comms), Requests, python-dotenv

### **Hardware & Platforms**
* **Edge Host:** Raspberry Pi (Frontend & Display controller)
* **Sensing:** ESP32-S3 mesh nodes (CSI sensing)
* **Display:** Freenove 800x480 DSI Touchscreen
* **Cloud Inference:** RunPod GPU Instances (DensePose server)

### **Cloud Services & APIs**
* **Voice & Audio:** ElevenLabs (TTS & Conversational AI), Twilio Voice API
* **Networking:** RunPod WebSocket proxy for live stream transport

### **Storage**
* **Logging:** Local JSONL event logging (tailed by the frontend for real-time motion event updates).

---

## **Getting Started**

### **Installation**
1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/JustinPMoran/lahacks-2026.git](https://github.com/JustinPMoran/lahacks-2026.git)
    cd lahacks-2026
    ```

2.  **Configure Environment:**
    Create a `.env` file in the root directory:
    ```env
    TWILIO_ACCOUNT_SID=your_sid
    TWILIO_AUTH_TOKEN=your_token
    ELEVENLABS_API_KEY=your_api_key
    RUNPOD_ENDPOINT=your_websocket_url
    ```

## **The Team**
Developed for **LA Hacks 2026**.
