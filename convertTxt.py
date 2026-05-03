import pickle

path = r"E:\Semester6\Laptrinhpython\project\ml_models\vectorizer.pkl"
output_txt = r"E:\Semester6\Laptrinhpython\project\ml_models\features.txt"

with open(path, "rb") as f:
    vectorizer = pickle.load(f)

features = vectorizer.get_feature_names_out()

with open(output_txt, "w", encoding="utf-8") as f:
    for term in features:
        f.write(term + "\n")

print("Đã lưu danh sách feature vào:", output_txt)