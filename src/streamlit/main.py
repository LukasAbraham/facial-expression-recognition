import os
import time
import tempfile

import streamlit as st
import numpy as np
import matplotlib.pyplot as plt
import cv2
from PIL import Image
import torch
from torchvision import transforms
from deepface import DeepFace
from deepface.modules import detection

from face_detector import FaceDetector

# Settings --------------------------------------------------------------------
use_cuda = torch.cuda.is_available()
device = 'cuda' if use_cuda else 'cpu'

MODELS_DIR = "../../models"

IMG_SIZE = 224

# Helpers ---------------------------------------------------------------------

class EmotionLabel:
    labels = [
        "Surprise",
        "Fear",
        "Disgust",
        "Happiness",
        "Sadness",
        "Anger",
        "Neutral"
    ]

    @staticmethod
    def get_label(index):
        return EmotionLabel.labels[index]

    @staticmethod
    def get_index(label):
        return EmotionLabel.labels.index(label)

def preprocess(img):
    test_transforms = transforms.Compose(
        [
            transforms.Resize((IMG_SIZE, IMG_SIZE)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406],
                                 std=[0.229, 0.224, 0.225])
        ]
    )

    img_tensor = test_transforms(img)
    img_tensor.unsqueeze_(0)

    return img_tensor

def predict_with_softmax(model, data):
    output = model(data)
    probabilities = torch.nn.functional.softmax(output, dim=1)
    return probabilities

# Demo ------------------------------------------------------------------------

models = {
    "affectnet_enet_b0",
    "affectnet_enet_b2",
    "raf_enet_b0",
    "raf_enet_b2",
    "raf_enet_b0_6epochs",
    "raf_enet_b0_10epochs",
}

face_detectors = {
    "opencv",
    "ssd",
    "dlib",
    "yolov8",
    "mtcnn",
    "retinaface",
}

def image_demo():
    st.title("Image demo")
    st.write(f"CUDA available? {use_cuda}")

    with st.sidebar:
        model_name = st.selectbox("Model", list(models))
        face_detector_type = st.selectbox("Face Detector", list(face_detectors))
        detection_threshold = st.slider("Detection Threshold", 0.0, 1.0, 0.5)
        enforce_detection = st.checkbox("Enforce face detection", value=False)
        align_face = st.checkbox("Align detected faces", value=False)

    uploaded_files = st.file_uploader("Uploaded image...", type=["png", "jpg"], accept_multiple_files=True)
    if uploaded_files is not None:
        cols = st.columns(len(uploaded_files))

        for i, uploaded_file in enumerate(uploaded_files):
            with cols[i]:
                st.image(uploaded_file)

        if st.button("Run"):
            for i, uploaded_file in enumerate(uploaded_files):
                # Reading the image using cv2.imdecode will create problems (e.g., unexpected number of detected faces)
                #   file_bytes = np.asarray(bytearray(uploaded_file.read()), dtype=np.uint8)
                #   img = cv2.imdecode(file_bytes, 1)

                tfile = tempfile.NamedTemporaryFile(delete=False)
                tfile.write(uploaded_file.getvalue())
                tfile.close()

                img = Image.open(uploaded_file)
                img = np.array(img)
                out_img = img.copy()

                # face_detector = FaceDetector(face_detector_type)
                model = torch.load(f"./models/{model_name.split('_')[0]}/{model_name}.pt", map_location=torch.device("cpu"))
                model = model.to(device)
                model.eval()

                # Face detection
                fd_start_time = time.time()

                # detected_faces = face_detector.detect_faces(img)
                # bboxes = face_detector.get_bboxes(detected_faces, detection_threshold)

                extracted_faces = DeepFace.extract_faces(tfile.name,
                                                         detector_backend=face_detector_type,
                                                         enforce_detection=enforce_detection,
                                                         align=align_face)

                fd_end_time = time.time()

                # FER
                fer_start_time = time.time()

                emotion_counts = {label: 0 for label in EmotionLabel.labels}

                emotions = []
                faces = []

                # for bbox in bboxes:
                #     x, y, w, h = bbox
                #
                #     face = img[y:y+h, x:x+w, :]
                #     faces.append(face)
                #
                #     img_tensor = preprocess(Image.fromarray(face))
                #
                #     scores = model(img_tensor.to(device))
                #     scores = scores[0].data.cpu().numpy()
                #
                #     emotion = EmotionLabel.get_label(np.argmax(scores))
                #     emotions.append(emotion)
                #     emotion_counts[emotion] += 1
                #
                #     cv2.rectangle(out_img, (x, y), (x + w, y + h), (0, 255, 0), 2)
                #     cv2.putText(out_img, emotion, (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (36,255,12), 2)

                for extracted_face in extracted_faces:
                    if extracted_face["confidence"] >= detection_threshold:
                        face = extracted_face["face"]
                        face = (face * 255).astype(np.uint8)
                        faces.append(face)

                        bbox = extracted_face["facial_area"]
                        x, y, w, h = bbox['x'], bbox['y'], bbox['w'], bbox['h']

                        img_tensor = preprocess(Image.fromarray(face))

                        # TODO: Use softmax
                        # scores = model(img_tensor.to(device))
                        scores = predict_with_softmax(model, img_tensor.to(device))
                        scores = scores[0].data.cpu().numpy()

                        emotion = EmotionLabel.get_label(np.argmax(scores))
                        emotions.append(emotion)
                        emotion_counts[emotion] += 1

                        cv2.rectangle(out_img, (x, y), (x + w, y + h), (0, 255, 0), 2)
                        cv2.putText(out_img, emotion, (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (36,255,12), 2)

                fer_end_time = time.time()

                # Save the output image
                output_filename = f"{os.path.splitext(uploaded_file.name)[0]}_{model_name}_{face_detector_type}_threshold{detection_threshold}_enforce-{str(enforce_detection).lower()}_align-{str(align_face).lower()}"
                output_image_name = f"./output/images/{output_filename}.png"
                cv2.imwrite(output_image_name, cv2.cvtColor(out_img, cv2.COLOR_RGB2BGR))

                with cols[i]:
                    st.image(out_img)
                    st.write(f"Face detection runtime: {format(fd_end_time - fd_start_time, '.2f')} seconds")
                    st.write(f"FER runtime: {format(fer_end_time - fer_start_time, '.2f')} seconds")
                    # st.write(f"Detected faces: {len(bboxes)}")
                    st.write(f"Detected faces: {len(extracted_faces)}")

                    # Plot the expression counts
                    fig, ax = plt.subplots()
                    bars = ax.bar(emotion_counts.keys(), emotion_counts.values(), color=plt.cm.get_cmap('rainbow', 7)(range(7)))
                    ax.set_xlabel("Expressions")
                    ax.set_ylabel("Frequency")
                    ax.set_title("Expression frequencies")
                    for bar in bars:
                        yval = bar.get_height()
                        ax.text(bar.get_x() + bar.get_width()/2.0 - 0.1, yval, round(yval, 2), va='bottom')
                    st.pyplot(fig)

                    # Save the plot
                    output_plot_name = f"./output/images/{output_filename}.pdf"
                    fig.savefig(output_plot_name)

                    for j in range(len(faces)):
                        face_container = st.container()
                        with face_container:
                            st.image(faces[j], caption=f"Face {j+1}")
                            st.write(f"Emotion: {emotions[j]}")

                os.remove(tfile.name)

def video_demo():
    st.title("Video demo")
    st.write(f"CUDA available? {use_cuda}")

    with st.sidebar:
        model_name = st.selectbox("Model", list(models))
        face_detector_type = st.selectbox("Detector", list(face_detectors))
        detection_threshold = st.slider("Threshold", 0.0, 1.0, 0.5)
        enforce_detection = st.checkbox("Enforce face detection", value=False)
        align_face = st.checkbox("Align detected faces", value=False)
        frame_skip = st.number_input("#Frames to skip", value=0)
        # fps = st.number_input("Output video's FPS", value=24.0)

    uploaded_files = st.file_uploader("Uploaded image...", type=["mp4", "mov"], accept_multiple_files=True)
    if uploaded_files is not None:
        cols = st.columns(len(uploaded_files))

        for i, uploaded_file in enumerate(uploaded_files):
            with cols[i]:
                st.video(uploaded_file)

        if st.button("Run"):
            for f, uploaded_file in enumerate(uploaded_files):
                tfile = tempfile.NamedTemporaryFile(delete=False)
                tfile.write(uploaded_file.read())
                tfile.close()

                emotion_counts = {label: 0 for label in EmotionLabel.labels}

                cap = cv2.VideoCapture(tfile.name)

                fps = cap.get(cv2.CAP_PROP_FPS)
                frame_width = int(cap.get(3))
                frame_height = int(cap.get(4))
                frame_count = 0

                fourcc = cv2.VideoWriter_fourcc(*'mp4v')

                file_extension = "mp4"
                out_filename = f"{uploaded_file.name.split('.')[0]}_{model_name}_{face_detector_type}_threshold{detection_threshold}_enforce-{str(enforce_detection).lower()}_align-{str(align_face).lower()}_fps{fps}_skip{frame_skip}"
                out = cv2.VideoWriter(f"./output/videos/{out_filename}.{file_extension}", fourcc, fps, (frame_width, frame_height))

                # face_detector = FaceDetector(face_detector_type)
                model = torch.load(f"./models/{model_name.split('_')[0]}/{model_name}.pt", map_location=torch.device("cpu"))
                model = model.to(device)
                model.eval()

                prev_bboxes = []
                prev_emotions = []
                prev_confidences = []

                while(cap.isOpened()):
                    ret, frame = cap.read()
                    if ret == True:
                        frame_count += 1
                        if frame_count % (frame_skip + 1) == 0:
                            prev_bboxes.clear()
                            prev_emotions.clear()
                            prev_confidences.clear()

                            extracted_faces = DeepFace.extract_faces(frame,
                                                                     detector_backend=face_detector_type,
                                                                     enforce_detection=enforce_detection,
                                                                     align=align_face)

                            for extracted_face in extracted_faces:
                                if extracted_face["confidence"] >= detection_threshold:
                                    face = extracted_face["face"]
                                    face = (face * 255).astype(np.uint8)

                                    bbox = extracted_face["facial_area"]
                                    x, y, w, h = bbox['x'], bbox['y'], bbox['w'], bbox['h']

                                    img_tensor = preprocess(Image.fromarray(face))

                                    # TODO: Use softmax
                                    # scores = model(img_tensor.to(device))
                                    scores = predict_with_softmax(model, img_tensor.to(device))
                                    scores = scores[0].data.cpu().numpy()

                                    emotion = EmotionLabel.get_label(np.argmax(scores))
                                    emotion_counts[emotion] += 1

                                    prev_bboxes.append([x, y, w, h])
                                    prev_emotions.append(emotion)
                                    prev_confidences.append(np.max(scores))

                                    cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
                                    cv2.putText(frame, f"{emotion} ({np.max(scores) * 100:.2f}%)", (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (36, 255, 12), 2)

                            # detected_faces = face_detector.detect_faces(frame)
                            # bboxes = face_detector.get_bboxes(detected_faces, detection_threshold)
                            #
                            # for bbox in bboxes:
                            #     x, y, w, h = bbox[0:4]
                            #     cropped_face = frame[y:y+h, x:x+w, :]
                            #
                            #     img_tensor = preprocess(Image.fromarray(cropped_face))
                            #
                            #     scores = model(img_tensor.to(device))
                            #     scores = scores[0].data.cpu().numpy()
                            #
                            #     emotion = EmotionLabel.get_label(np.argmax(scores))
                            #     emotion_counts[emotion] += 1
                            #
                            #     prev_bboxes.append([x, y, w, h])
                            #     prev_emotions.append(emotion)
                            #     prev_confidences.append(np.max(scores))
                            #
                            #     cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
                            #     cv2.putText(frame, f"{emotion} ({np.max(scores) * 100:.2f}%)", (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (36, 255, 12), 2)
                        else:
                            for i in range(len(prev_bboxes)):
                                x, y, w, h = prev_bboxes[i]
                                emotion = prev_emotions[i]
                                score = prev_confidences[i]
                                cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
                                cv2.putText(frame, f"{emotion} ({score * 100:.2f}%)", (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (36, 255, 12), 2)

                        out.write(frame)
                    else:
                        break;

                st.write(f"Frame rate: {fps}")

                cap.release()
                out.release()
                cv2.destroyAllWindows()

                video_file = open(f"./output/videos/{out_filename}.{file_extension}", 'rb')
                video_bytes = video_file.read()
                st.video(video_bytes)

                with cols[f]:
                    mean_emotion_mean_freq = {emotion: count / (frame_count / (frame_skip + 1)) for emotion, count in emotion_counts.items()}
                    mean_emotion_freq = {emotion: count for emotion, count in emotion_counts.items()}

                    emotions = list(mean_emotion_freq.keys())
                    freqs = list(mean_emotion_freq.values())
                    mean_freqs = list(mean_emotion_mean_freq.values())

                    fig, ax = plt.subplots()
                    bars = ax.bar(emotions, freqs, color=plt.cm.get_cmap('rainbow', len(emotions))(range(len(emotions))))
                    ax.set_xlabel("Expressions")
                    ax.set_ylabel("Frequencies")
                    ax.set_title("Expression frequencies")
                    for bar in bars:
                        yval = bar.get_height()
                        ax.text(bar.get_x() + bar.get_width()/2.0 - 0.1, yval, round(yval, 2), va='bottom')
                    st.pyplot(fig)

                    # Save the plot
                    output_plot_name = f"./output/videos/{out_filename}_freq_plot.pdf"
                    fig.savefig(output_plot_name)

                    fig, ax = plt.subplots()
                    bars = ax.bar(emotions, mean_freqs, color=plt.cm.get_cmap('rainbow', 7)(range(7)))
                    ax.set_xlabel("Expressions")
                    ax.set_ylabel("Mean Frequencies")
                    ax.set_title("Expression mean frequencies")
                    for bar in bars:
                        yval = bar.get_height()
                        ax.text(bar.get_x() + bar.get_width()/2.0 - 0.1, yval, round(yval, 2), va='bottom')
                    st.pyplot(fig)

                    # Save the mean frequencies plot
                    output_mean_freq_plot_name = f"./output/videos/{out_filename}_mean_freq_plot.pdf"
                    fig.savefig(output_mean_freq_plot_name)

                # Remove the temoporary file when done
                time.sleep(1) # takes some time to be able to remove
                os.remove(tfile.name)

apps = {
    "image_demo",
    "video_demo"
}

with st.sidebar:
    app = st.selectbox("Demo", list(apps))

if app == "image_demo":
    image_demo()
elif app == "video_demo":
    video_demo()
