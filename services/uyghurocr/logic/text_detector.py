import cv2
import numpy as np
import onnxruntime as ort
import pyclipper
from typing import List, Tuple

class TextDetector:
    def __init__(self, model_path: str):
        self.min_size = 2
        self.thresh = 0.2
        self.box_thresh = 0.5
        self.shortest_size = 1280
        self.limit_size = 1600
        self.unclip_ratio = 5.0
        self.max_candidates = 1500
        self.mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        self.std = np.array([0.229, 0.224, 0.225], dtype=np.float32)

        self.session = ort.InferenceSession(model_path)
        self.input_name = self.session.get_inputs()[0].name

    def resize_shortest_edge(self, img: np.ndarray) -> np.ndarray:
        h, w = img.shape[:2]
        scale = self.shortest_size / min(h, w)
        
        if h < w:
            new_h = self.shortest_size
            new_w = int(w * scale)
        else:
            new_w = self.shortest_size
            new_h = int(h * scale)

        if max(new_h, new_w) > self.limit_size:
            scale = self.limit_size / max(new_h, new_w)
            new_h = int(new_h * scale)
            new_w = int(new_w * scale)

        new_w = max((new_w // 32) * 32, 32)
        new_h = max((new_h // 32) * 32, 32)

        resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
        return cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)

    def preprocess(self, img: np.ndarray) -> np.ndarray:
        resized = self.resize_shortest_edge(img)
        img_data = resized.astype(np.float32) / 255.0
        img_data = (img_data - self.mean) / self.std
        img_data = img_data.transpose(2, 0, 1)  # HWC to CHW
        return img_data[np.newaxis, :]  # Add batch dimension

    def detect(self, img: np.ndarray) -> Tuple[List[np.ndarray], np.ndarray]:
        ori_h, ori_w = img.shape[:2]
        input_tensor = self.preprocess(img)
        
        outputs = self.session.run(None, {self.input_name: input_tensor})
        pred = outputs[0][0, 0, :, :]
        
        binary = (pred > self.thresh).astype(np.uint8) * 255
        
        boxes, scores = self.boxes_from_bitmap(pred, binary, ori_w, ori_h)
        return boxes, scores

    def boxes_from_bitmap(self, pred: np.ndarray, binary: np.ndarray, dest_width: int, dest_height: int) -> Tuple[List[np.ndarray], np.ndarray]:
        height, width = binary.shape
        contours, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        num_contours = min(len(contours), self.max_candidates)

        boxes = []
        scores = []

        for i in range(num_contours):
            contour = contours[i]
            points, sside = self.get_mini_boxes(contour)

            if sside < self.min_size:
                continue

            score = self.box_score_fast(pred, contour)
            if self.box_thresh > score:
                continue

            box = self.unclip(points, self.unclip_ratio)
            if len(box) == 0:
                continue
            
            box = box.reshape(-1, 2)
            new_box, new_sside = self.get_mini_boxes(box)
            if new_sside < self.min_size + 2:
                continue

            # Scale to original image size
            scaled_box = new_box.astype(np.float32)
            scaled_box[:, 0] = np.clip(np.round(scaled_box[:, 0] * dest_width / width), 0, dest_width)
            scaled_box[:, 1] = np.clip(np.round(scaled_box[:, 1] * dest_height / height), 0, dest_height)

            boxes.append(scaled_box.astype(np.int32))
            scores.append(score)

        return boxes, np.array(scores)

    def unclip(self, box: np.ndarray, unclip_ratio: float) -> np.ndarray:
        # DBNet unclip logic
        # area = cv2.contourArea(box)
        # perimeter = cv2.arcLength(box, True)
        
        # Original C# code calculation:
        area = 0
        perimeter = 0
        for i in range(len(box)):
            j = (i + 1) % len(box)
            area += box[i][0] * box[j][1] - box[j][0] * box[i][1]
            perimeter += np.sqrt((box[j][0] - box[i][0])**2 + (box[j][1] - box[i][1])**2)
        area = abs(area / 2.0)
        
        width = box[:, 0].max() - box[:, 0].min()
        height = box[:, 1].max() - box[:, 1].min()
        box_dist = min(width, height)
        
        if perimeter == 0 or box_dist == 0:
            return box

        ratio = unclip_ratio / np.sqrt(box_dist)
        distance = area * ratio / perimeter

        pco = pyclipper.PyclipperOffset()
        pco.AddPath(box, pyclipper.JT_ROUND, pyclipper.ET_CLOSEDPOLYGON)
        
        # Scaling for precision match with C# (which used 1000.0)
        # Actually pyclipper handles it internally or we can scale. 
        # C# used: clipper.Execute(distance * scale, solution); where scale = 1000.0
        
        expanded = pco.Execute(distance)
        if not expanded:
            return np.array([])
        return np.array(expanded[0])

    def get_mini_boxes(self, contour: np.ndarray) -> Tuple[np.ndarray, float]:
        rect = cv2.minAreaRect(contour)
        points = cv2.boxPoints(rect)
        
        # Sorting matches C# logic
        points = points[np.argsort(points[:, 0])]
        index1 = 0 if points[1, 1] > points[0, 1] else 1
        index4 = 1 if index1 == 0 else 0
        index2 = 2 if points[3, 1] > points[2, 1] else 3
        index3 = 3 if index2 == 2 else 2
        
        box = np.array([points[index1], points[index2], points[index3], points[index4]])
        return box, min(rect[1])

    def box_score_fast(self, pred: np.ndarray, contour: np.ndarray) -> float:
        h, w = pred.shape
        contour = contour.copy()
        xmin = np.clip(np.floor(contour[:, 0, 0].min()).astype(np.int32), 0, w - 1)
        xmax = np.clip(np.ceil(contour[:, 0, 0].max()).astype(np.int32), 0, w - 1)
        ymin = np.clip(np.floor(contour[:, 0, 1].min()).astype(np.int32), 0, h - 1)
        ymax = np.clip(np.ceil(contour[:, 0, 1].max()).astype(np.int32), 0, h - 1)

        mask = np.zeros((ymax - ymin + 1, xmax - xmin + 1), dtype=np.uint8)
        shifted_contour = contour.copy()
        shifted_contour[:, 0, 0] -= xmin
        shifted_contour[:, 0, 1] -= ymin
        cv2.fillPoly(mask, [shifted_contour.astype(np.int32)], 1)
        
        return cv2.mean(pred[ymin:ymax+1, xmin:xmax+1], mask=mask)[0]
