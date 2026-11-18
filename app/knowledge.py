"""Base de conhecimento de veículos e peças (fácil de ampliar)."""

# modelo (normalizado, tokens separados por espaço) -> montadora
MODELS: dict[str, str] = {}

_BY_BRAND = {
    "Volkswagen": "gol voyage saveiro fox crossfox spacefox polo virtus up jetta golf|t cross|nivus|amarok|tiguan|parati|kombi|fusca|taos",
    "Chevrolet": "onix prisma cruze celta corsa cobalt spin s10 tracker montana agile classic|vectra|astra|meriva|zafira|equinox|trailblazer|captiva",
    "Fiat": "palio uno strada siena toro argo mobi cronos punto idea doblo fiorino pulse fastback|grand siena|linea|bravo|freemont|weekend",
    "Ford": "ka fiesta ecosport focus ranger fusion territory|courier|edge|maverick|bronco",
    "Hyundai": "hb20 hb20s creta tucson i30 ix35|azera|elantra|santa fe",
    "Toyota": "corolla etios yaris hilux sw4|corolla cross|rav4|prius",
    "Honda": "civic fit city|hr v|wr v|cr v|accord",
    "Renault": "sandero logan duster kwid clio captur oroch|stepway|fluence|megane|master",
    "Nissan": "march versa kicks sentra frontier|livina|tiida",
    "Peugeot": "206 207 208 3008 307 308 408|partner|expert",
    "Citroen": "c3 c4|c4 cactus|c4 lounge|aircross|jumpy",
    "Jeep": "renegade compass commander wrangler",
    "Mitsubishi": "l200 pajero outlander asx|lancer|eclipse cross",
}
for _brand, _spec in _BY_BRAND.items():
    # 1º bloco: modelos de uma palavra separados por espaço; demais blocos: nomes compostos
    _single, *_multi = _spec.split("|")
    for _name in _single.split() + [m.strip() for m in _multi]:
        MODELS[_name] = _brand

BRANDS = {
    "vw": "Volkswagen", "volkswagen": "Volkswagen", "volks": "Volkswagen",
    "chevrolet": "Chevrolet", "gm": "Chevrolet", "chevy": "Chevrolet",
    "fiat": "Fiat", "ford": "Ford", "hyundai": "Hyundai", "toyota": "Toyota",
    "honda": "Honda", "renault": "Renault", "nissan": "Nissan", "peugeot": "Peugeot",
    "citroen": "Citroen", "jeep": "Jeep", "mitsubishi": "Mitsubishi",
}

# Marcas de fabricantes de autopeças
PART_BRANDS = {
    "bosch": "Bosch", "cofap": "Cofap", "monroe": "Monroe", "nakata": "Nakata",
    "trw": "TRW", "frasle": "Fras-le", "fras": "Fras-le", "cobreq": "Cobreq",
    "valeo": "Valeo", "skf": "SKF", "ngk": "NGK", "mahle": "Mahle", "tecfil": "Tecfil",
    "fram": "Fram", "wega": "Wega", "mann": "Mann", "sachs": "Sachs", "gates": "Gates",
    "dayco": "Dayco", "continental": "Continental", "magneti": "Magneti Marelli",
    "marelli": "Magneti Marelli", "delphi": "Delphi", "syl": "Syl", "jurid": "Jurid",
    "hipper": "Hipper Freios", "vetor": "Vetor", "axios": "Axios", "kayaba": "Kayaba",
    "kyb": "Kayaba", "luk": "LUK", "ina": "INA", "fag": "FAG", "nytron": "Nytron",
    "denso": "Denso", "motorcraft": "Motorcraft", "acdelco": "ACDelco", "mopar": "Mopar",
}

STOPWORDS = {
    "de", "do", "da", "dos", "das", "para", "pra", "p", "com", "e", "o", "a", "os",
    "as", "em", "no", "na", "ano", "modelo", "carro", "veiculo", "um", "uma", "ate",
    "ao", "lado", "motor",
}

# Palavras que não são obrigatórias no título (anúncios variam muito)
SOFT_WORDS = {"kit", "jogo", "par", "unidade", "peca", "original", "novo", "nova", "conjunto", "jg"}

# Sinônimos: o anúncio pode usar qualquer uma das formas
SYNONYMS = {
    "gasolina": {"combustivel"},
    "combustivel": {"gasolina"},
    "pastilha": {"pastilha"},
    "lona": {"sapata", "lona"},
    "sapata": {"lona", "sapata"},
    "coxim": {"calco", "coxim"},
    "calco": {"coxim", "calco"},
    "bieleta": {"tirante", "bieleta"},
    "rolamento": {"rolamento", "cubo"},
    "farol": {"farol", "optico"},
    "radiador": {"radiador"},
    "vela": {"vela"},
    "correia": {"correia"},
    "embreagem": {"embreagem", "embreage"},
}

POSITIONS = {"dianteiro": "dianteira", "dianteira": "dianteira", "diant": "dianteira",
             "traseiro": "traseira", "traseira": "traseira", "tras": "traseira"}
SIDES = {"esquerdo": "esquerdo", "esquerda": "esquerdo", "le": "esquerdo",
         "direito": "direito", "direita": "direito", "ld": "direito"}

ENGINE_TAGS = {"8v", "16v", "12v", "turbo", "tsi", "flex", "diesel", "aspirado", "mpi", "msi", "gti"}

# Palavras que indicam acessório/componente, não a peça em si (ex.: "parafuso da pinça")
ACCESSORY_WORDS = {
    "parafuso", "porca", "arruela", "pino", "presilha", "grampo", "trava", "reparo",
    "suporte", "sensor", "capa", "adesivo", "chaveiro", "protetor", "bucha", "borracha",
    "chicote", "soquete", "lampada", "moldura", "aplique", "emblema", "guarnicao", "miniatura",
}
