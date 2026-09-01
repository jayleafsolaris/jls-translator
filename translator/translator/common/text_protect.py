"""
Placeholder/token protection (so color codes and %1$s-style format specs
survive translation untouched) and the American -> British spelling
conversion used for en_GB.
"""
import re
from .state import TOKEN_PATTERN
_SPLIT_PATTERN = re.compile(f"({TOKEN_PATTERN.pattern})")
_KEY_REF_RE = re.compile(r"\{([^{}]+)\}")
BRITISH_SPELLINGS = {
    "color": "colour", "colors": "colours", "colored": "coloured",
    "coloring": "colouring", "colorful": "colourful", "discolor": "discolour",
    "discolored": "discoloured", "favorite": "favourite", "favorites": "favourites", 
    "favor": "favour", "favors": "favours", "favored": "favoured", "favoring": "favouring",
    "honor": "honour", "honors": "honours", "honored": "honoured",
    "honoring": "honouring", "honorable": "honourable", "humor": "humour", 
    "humors": "humours", "humored": "humoured", "humorous": "humourous",
    "flavor": "flavour", "flavors": "flavours", "flavored": "flavoured",
    "flavoring": "flavouring", "behavior": "behaviour", "behaviors": "behaviours",
    "behavioral": "behavioural", "neighbor": "neighbour", "neighbors": "neighbours",
    "neighborhood": "neighbourhood", "neighborhoods": "neighbourhoods",
    "labor": "labour", "labors": "labours", "labored": "laboured",
    "rumor": "rumour", "rumors": "rumours", "armor": "armour", "armors": "armours", 
    "armored": "armoured", "harbor": "harbour", "harbors": "harbours",
    "vapor": "vapour", "vapors": "vapours", "savior": "saviour", "saviors": "saviours",
    "organize": "organise", "organizes": "organises", "organized": "organised", 
    "organizing": "organising", "organization": "organisation", 
    "organizations": "organisations", "realize": "realise", "realizes": "realises", 
    "realized": "realised", "realizing": "realising", "recognize": "recognise", 
    "recognizes": "recognises", "recognized": "recognised", "recognizing": "recognising",
    "apologize": "apologise", "apologizes": "apologises", "apologized": "apologised", 
    "apologizing": "apologising", "customize": "customise", "customizes": "customises",
    "customized": "customised", "customizing": "customising", "customizable": "customisable",
    "analyze": "analyse", "analyzes": "analyses", "analyzed": "analysed",
    "analyzing": "analising", "catalog": "catalogue", "catalogs": "catalogues",
    "dialog": "dialogue", "dialogs": "dialogues", "theater": "theatre", 
    "theaters": "theatres", "center": "centre", "centers": "centres", 
    "centered": "centred", "centering": "centring", "fiber": "fibre", 
    "fibers": "fibres", "defense": "defence", "defenses": "defences",
    "offense": "offence", "offenses": "offences", "license": "licence", 
    "licenses": "licences", "gray": "grey", "grays": "greys", "grayed": "greyed",
    "grayscale": "greyscale", "canceled": "cancelled", "canceling": "cancelling",
    "traveled": "travelled", "traveling": "travelling", "traveler": "traveller", 
    "travelers": "travellers", "modeled": "modelled", "modeling": "modelling",
    "jewelry": "jewellery", "aluminum": "aluminium", "skeptic": "sceptic", 
    "skeptics": "sceptics", "skeptical": "sceptical", "mustache": "moustache", 
    "mustaches": "moustaches", "mold": "mould", "molds": "moulds", 
    "molded": "moulded", "molding": "moulding", "plow": "plough", "plows": "ploughs",
}
_WORD_PATTERN = re.compile(r"[A-Za-z]+")
from ..functions._match_case import _match_case
from ..functions._protect import _protect
from ..functions._restore import _restore
from ..functions.apply_token_patch import apply_token_patch
from ..functions.join_segments import join_segments
from ..functions.resolve_key_references import resolve_key_references
from ..functions.split_segments import split_segments
from ..functions.to_british import to_british
from ..functions.tokens_only_diff import tokens_only_diff
