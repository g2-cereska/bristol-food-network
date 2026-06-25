import random
from datetime import date, timedelta

from fastapi import FastAPI

app = FastAPI(title='Bristol Food Network AI Service')

MODEL_VERSION = 'baseline-v1'

# A small in-memory product catalogue used to generate plausible demo
# responses. In a production system this would be replaced by a real
# trained model reading from the marketplace database.
SAMPLE_PRODUCTS = [
    {'id': 1, 'name': 'Organic Carrots', 'producer_name': 'Bristol Valley Farm'},
    {'id': 2, 'name': 'Heritage Tomatoes', 'producer_name': 'Bristol Valley Farm'},
    {'id': 3, 'name': 'Bramley Apples', 'producer_name': 'Bristol Valley Farm'},
    {'id': 4, 'name': 'Whole Milk 1L', 'producer_name': 'Hillside Dairy'},
    {'id': 5, 'name': 'Farmhouse Cheddar', 'producer_name': 'Hillside Dairy'},
]


@app.get('/health')
def health():
    return {'status': 'ok'}


@app.get('/recommend/{customer_id}')
def recommend(customer_id: int):
    """
    Returns personalised product recommendations for a customer.

    This is a simplified baseline: it ranks the sample catalogue by a
    random relevance score and returns the top three, along with a
    short explanation for each. A production version would train on
    UserInteraction history (views, cart adds, purchases) using a
    collaborative-filtering or content-based approach.
    """
    random.seed(customer_id)
    scored = [
        {**product, 'score': round(random.uniform(0.5, 0.99), 2)}
        for product in SAMPLE_PRODUCTS
    ]
    top_picks = sorted(scored, key=lambda item: item['score'], reverse=True)[:3]

    recommendations = [
        {
            'product_id': pick['id'],
            'product_name': pick['name'],
            'producer_name': pick['producer_name'],
            'confidence': pick['score'],
            'explanation': f"Recommended based on similarity to items customer {customer_id} has viewed.",
        }
        for pick in top_picks
    ]

    return {
        'customer_id': customer_id,
        'model_version': MODEL_VERSION,
        'recommendations': recommendations,
    }


@app.get('/forecast/{producer_id}')
def forecast(producer_id: int):
    """
    Returns a simple weekly demand forecast per product for a producer.

    Baseline implementation: generates a plausible forecast curve using
    a seeded random walk so results are deterministic per producer.
    A production version would use historical order volume with a
    time-series model (e.g. exponential smoothing or Prophet).
    """
    random.seed(producer_id)
    today = date.today()
    forecast_days = []
    base_demand = random.randint(10, 30)

    for day_offset in range(7):
        day = today + timedelta(days=day_offset)
        demand = max(0, base_demand + random.randint(-5, 5))
        forecast_days.append({
            'date': day.isoformat(),
            'predicted_units': demand,
        })

    return {
        'producer_id': producer_id,
        'model_version': MODEL_VERSION,
        'forecast': forecast_days,
        'confidence': round(random.uniform(0.6, 0.9), 2),
    }


@app.post('/quality-grade')
def quality_grade(payload: dict):
    """
    Grades produce quality as A, B, or C based on submitted attributes.

    Baseline rule-based implementation using days-since-harvest and a
    visual defect score (0-1, where 0 is perfect). A production version
    would replace this with a trained computer vision classifier.
    """
    days_since_harvest = payload.get('days_since_harvest', 0)
    defect_score = payload.get('defect_score', 0.0)

    if days_since_harvest <= 2 and defect_score < 0.1:
        grade = 'A'
    elif days_since_harvest <= 5 and defect_score < 0.3:
        grade = 'B'
    else:
        grade = 'C'

    return {
        'grade': grade,
        'days_since_harvest': days_since_harvest,
        'defect_score': defect_score,
        'model_version': MODEL_VERSION,
    }