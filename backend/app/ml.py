"""Optional candidate ranking. This module cannot accept matches or write records."""
from datetime import date
from difflib import SequenceMatcher


def text_similarity(left,right):
    if not left or not right:
        return 0.0
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    try:
        vectors=TfidfVectorizer(analyzer='char',ngram_range=(2,4)).fit_transform([left,right])
        return float(cosine_similarity(vectors[0],vectors[1])[0,0])
    except ValueError:
        return float(left==right)


def features(a, b):
    # Floats are allowed for ML features only; monetary equality stays in Decimal.
    similarity = lambda x, y: SequenceMatcher(None, x, y).ratio() if x and y else 0.0
    return [float(abs(a.amount-b.amount)), abs((date.fromisoformat(a.date)-date.fromisoformat(b.date)).days),
        similarity(a.reference,b.reference), text_similarity(a.description,b.description),
        similarity(a.counterparty,b.counterparty), int(a.currency==b.currency), int(a.account==b.account)]


def train_and_evaluate(train_x, train_y, test_x, test_y, kind='logistic'):
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import precision_score, recall_score, brier_score_loss
    if kind not in ('logistic','random_forest'):
        raise ValueError('Unsupported ranker kind')
    model = make_pipeline(StandardScaler(), LogisticRegression(random_state=42, max_iter=1000)) if kind == 'logistic' else RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(train_x, train_y)
    predictions = model.predict(test_x)
    scores = model.predict_proba(test_x)[:,1]
    reliability=[]
    for index in range(10):
        selected=[i for i,value in enumerate(scores) if int(min(float(value)*10,9))==index]
        if selected:
            reliability.append({'bin':index,'count':len(selected),'mean_score':float(sum(scores[i] for i in selected)/len(selected)),
                'observed_match_rate':sum(test_y[i] for i in selected)/len(selected)})
    return model, {'version':'candidate-ranker-v2-tfidf', 'kind':kind, 'precision':float(precision_score(test_y,predictions,zero_division=0)),
        'recall':float(recall_score(test_y,predictions,zero_division=0)), 'brier_score':float(brier_score_loss(test_y,scores)),
        'reliability_bins':reliability,
        'calibrated':False, 'note':'Held-out synthetic-pair results do not establish production calibration.'}
