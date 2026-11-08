"""Constantes partagées entre l'entraînement et le service d'inférence.

Toute modification ici (taille d'image, normalisation, ordre des classes)
change le contrat entre le modèle et l'API : elle est donc exportée dans
`preprocessing.json` avec chaque version du modèle.
"""

# Classes EuroSAT (ordre alphabétique = ordre d'ImageFolder)
CLASSES = [
    "AnnualCrop",
    "Forest",
    "HerbaceousVegetation",
    "Highway",
    "Industrial",
    "Pasture",
    "PermanentCrop",
    "Residential",
    "River",
    "SeaLake",
]

# Les images EuroSAT font 64x64 ; on sur-échantillonne à 128 pour mieux
# exploiter les filtres pré-entraînés sur ImageNet sans exploser le coût CPU.
IMG_SIZE = 128

# Normalisation ImageNet (backbones pré-entraînés)
MEAN = [0.485, 0.456, 0.406]
STD = [0.229, 0.224, 0.225]

REGISTERED_MODEL_NAME = "eurosat-classifier"
SEED = 42
