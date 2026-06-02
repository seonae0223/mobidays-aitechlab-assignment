.PHONY: run dashboard install

install:
	pip3 install -r requirements.txt

run:
	python3 main.py --input json --file "data/노바드림_20260601_캠페인사전정렬회의.json"

run-mp3:
	python3 main.py --input mp3 --file "data/노바드림_20260601_캠페인사전정렬회의.mp3"

dashboard:
	streamlit run dashboard/app.py
