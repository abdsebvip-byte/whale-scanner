# Phase 3 — Track 1: Feature Engineering → ML Engine → Ensemble

## المسار
Track 1 من 4 (الأولوية الأولى — الأكثر تأثيراً على دقة الاكتشاف)

## المكونات الجديدة

### 1. feature_pipeline.py
- يستخرج 25+ ميزة من OHLCV
- يخزن في feature_store.db
- الميزات: 6 موجودة + 4 MACD + 3 SMA/EMA + 3 ADX + 1 ATR + 5 سياقية = 22

### 2. ml_engine.py
- FeaturePipeline: يحول OHLCV → feature vector
- MLModelTrainer: يدرب 3 نماذج (XGBoost, RF, Neural Net 1-layer)
- EnsemblePredictor: VotingClassifier(soft, weights=[3,2,1])
- BacktestValidator: accuracy, precision, recall, F1, confusion matrix
- predict(symbol, features) → probability 0.0-1.0

### 3. feature_store.db
- جدول `feature_vectors`: id, symbol, timestamp, target (0/1), features (JSON)

### 4. train_models.py
- سكريبت تدريب مستقل
- SMOTE للتوازن
- train_ml() بعد كل 50 outcome / يدوي

## الملفات المعدلة

### 5. predictive_scanner.py
- استبدال weighted sum الحالي بـ ML prediction
- إذا ML غير جاهز → fallback للوزن الثابت

### 6. signals.py
- classify_signal من lift بسيط → ML probability + threshold

## خريطة العمل

| الخطوة | الملف | الوصف |
|--------|-------|-------|
| 1 | feature_pipeline.py | بناء pipeline الميزات الـ 22 |
| 2 | feature_store.db | schema + تخزين |
| 3 | test_features.py | 30+ اختبار للميزات |
| 4 | ml_engine.py | التدريب + التنبؤ + ensemble |
| 5 | train_models.py | سكريبت تدريب مع SMOTE |
| 6 | test_ml.py | 50+ اختبار للنماذج |
| 7 | تعديل predictive_scanner.py | ربط ML |
| 8 | تعديل signals.py | تصنيف ديناميكي |
| 9 | test_integration.py | حلقة كاملة ← signal |
| 10 | تشغيل التدريب | train_models.py على 400 outcome |
