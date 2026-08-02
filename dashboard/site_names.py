"""Human-readable labels for NHS Scotland A&E treatment-location codes."""

SITE_NAMES = {
    "A111H": "University Hospital Crosshouse",
    "A210H": "University Hospital Ayr",
    "B120H": "Borders General Hospital",
    "C121H": "Lorn & Islands Hospital",
    "C313H": "Inverclyde Royal Hospital",
    "C418H": "Royal Alexandra Hospital",
    "F704H": "Victoria Hospital (NHS Fife)",
    "F805H": "Queen Margaret Hospital",
    "G107H": "Glasgow Royal Infirmary",
    "G207H": "New Stobhill Hospital",
    "G306H": "New Victoria Hospital",
    "G405H": "Queen Elizabeth University Hospital",
    "G513H": "Royal Hospital for Children Glasgow",
    "G516H": "West Glasgow Ambulatory Care Hospital",
    "H103H": "Caithness General Hospital",
    "H202H": "Raigmore Hospital",
    "H212H": "Belford Hospital",
    "L106H": "University Hospital Monklands",
    "L302H": "University Hospital Hairmyres",
    "L308H": "University Hospital Wishaw",
    "N101H": "Aberdeen Royal Infirmary",
    "N121H": "Royal Aberdeen Children's Hospital",
    "N411H": "Dr Gray's Hospital",
    "R103H": "Balfour Hospital",
    "S308H": "St John's Hospital",
    "S314H": "Royal Infirmary of Edinburgh",
    "S319H": "Royal Hospital for Children and Young People (Edinburgh)",
    "T101H": "Ninewells Hospital",
    "T202H": "Perth Royal Infirmary",
    "V201H": "Stirling Health and Care Village",
    "V217H": "Forth Valley Royal Hospital",
    "W107H": "Western Isles Hospital",
    "Y144H": "Galloway Community Hospital",
    "Y146H": "Dumfries & Galloway Royal Infirmary",
    "Z102H": "Gilbert Bain Hospital",
}


def site_label(site_code: object) -> str:
    """Return a readable label while preserving the source code for traceability."""
    code = str(site_code)
    name = SITE_NAMES.get(code)
    return f"{name} ({code})" if name else code
