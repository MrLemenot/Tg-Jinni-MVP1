install:
	pip install -r requirements.txt

api:
	uvicorn app.main:app --reload --port 8000

bot:
	python -m app.bot.bot

worker:
	python -m app.tasks.worker

test:
	pytest -q
