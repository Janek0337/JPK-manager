import pandas as pd
from lxml import etree
from datetime import datetime
from utils import XSD_FILES_PATH, XML_FILES_PATH
import database as db
from sqlalchemy.orm import Session

separator = "\t"
naglowki_cols = {'IBAN', 'Okres_YYYYMM', 'Waluta', 'Saldo_Poczatkowe', 'Saldo_Koncowe'}
pozycje_cols = {'IBAN', 'Okres_YYYYMM', 'Numer_Wiersza', 'Data_Operacji', 'Nazwa_Podmiotu', 'Opis_Operacji', 'Kwota_Operacji', 'Saldo_Operacji'}

def _read_input_files(naglowki_path: str, pozycje_path: str):

    naglowki = pd.read_csv(naglowki_path, sep=separator, dtype=str)
    if set(naglowki.columns) != naglowki_cols:
        raise ValueError("Zła struktura pliku nagłówkowego")

    pozycje = pd.read_csv(pozycje_path, sep=separator, dtype=str)
    if set(pozycje.columns) != pozycje_cols:
        raise ValueError("Zła struktura pliku z pozycjami")

    df = pd.merge(pozycje, naglowki, how='left', on=['IBAN', 'Okres_YYYYMM'])

    if df['Waluta'].isna().any():
        raise ValueError("Znaleziono pozycje wyciągu bez pasującego nagłówka!")

    return df


def _validate_sums(df: pd.DataFrame) -> tuple:
    kolumny_kwotowe = ['Saldo_Poczatkowe', 'Saldo_Koncowe', 'Kwota_Operacji', 'Saldo_Operacji']
    for col in kolumny_kwotowe:
        df[col] = pd.to_numeric(df[col].str.replace(',', '.'), errors='coerce')
        
    df['Numer_Wiersza'] = df['Numer_Wiersza'].astype(int)

    grupy = df.groupby(['IBAN', 'Okres_YYYYMM'])
    
    sumy_kontrolne = {}

    for (iban, okres), paczka_df in grupy:
        liczba_operacji = len(paczka_df)

        oczekiwana_numeracja = list(range(1, liczba_operacji + 1))
        if list(paczka_df['Numer_Wiersza']) != oczekiwana_numeracja:
            raise ValueError(f"Numeracja nie zgadza się dla rachunku {iban} miesiąc {okres}")

        suma_uznan = paczka_df[paczka_df['Kwota_Operacji'] > 0]['Kwota_Operacji'].sum()
        suma_obciazen = abs(paczka_df[paczka_df['Kwota_Operacji'] < 0]['Kwota_Operacji'].sum())

        saldo_poczatkowe = paczka_df['Saldo_Poczatkowe'].iloc[0]
        saldo_koncowe = paczka_df['Saldo_Koncowe'].iloc[0]

        if round(saldo_poczatkowe + suma_uznan - suma_obciazen, 2) != round(saldo_koncowe, 2):
            raise ValueError(f"Salda się nie zgadzają dla rachunku {iban} miesiąc {okres}")
            
        sumy_kontrolne[(iban, okres)] = {
            'LiczbaWierszy': liczba_operacji,
            'SumaUznan': round(suma_uznan, 2),
            'SumaObciazen': round(suma_obciazen, 2)
        }

        return (df, sumy_kontrolne)


def _generuj_xml_dla_wyciagu(iban: str, okres_yyyymm: str, paczka_df: pd.DataFrame, sumy_kontrolne: dict, podmiot_dane: dict) -> etree.ElementTree:
    NSMAP = {
        'tns': 'http://jpk.mf.gov.pl/wzor/2016/03/09/03092/',
        'etd': 'http://crd.gov.pl/xml/schematy/dziedzinowe/mf/2016/01/25/eD/DefinicjeTypy/',
        'kck': 'http://crd.gov.pl/xml/schematy/dziedzinowe/mf/2013/05/23/eD/KodyCECHKRAJOW/'
    }
    TNS = f"{{{NSMAP['tns']}}}"
    ETD = f"{{{NSMAP['etd']}}}"

    root = etree.Element(f"{TNS}JPK", nsmap=NSMAP)

    naglowek = etree.SubElement(root, f"{TNS}Naglowek")
    etree.SubElement(naglowek, f"{TNS}KodFormularza", kodSystemowy="JPK_WB (1)", wersjaSchemy="1-0").text = "JPK_WB"
    etree.SubElement(naglowek, f"{TNS}WariantFormularza").text = "1"
    etree.SubElement(naglowek, f"{TNS}CelZlozenia").text = "1"
    
    etree.SubElement(naglowek, f"{TNS}DataWytworzeniaJPK").text = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    
    rok, miesiac = int(okres_yyyymm[:4]), int(okres_yyyymm[4:])
    ostatni_dzien = pd.Period(f'{rok}-{miesiac}').days_in_month
    etree.SubElement(naglowek, f"{TNS}DataOd").text = f"{rok}-{miesiac:02d}-01"
    etree.SubElement(naglowek, f"{TNS}DataDo").text = f"{rok}-{miesiac:02d}-{ostatni_dzien}"
    
    waluta = str(paczka_df['Waluta'].iloc[0])
    etree.SubElement(naglowek, f"{TNS}DomyslnyKodWaluty").text = waluta
    etree.SubElement(naglowek, f"{TNS}KodUrzedu").text = podmiot_dane['kod_urzedu']

    podmiot1 = etree.SubElement(root, f"{TNS}Podmiot1")
    identyfikator = etree.SubElement(podmiot1, f"{TNS}IdentyfikatorPodmiotu")
    etree.SubElement(identyfikator, f"{ETD}NIP").text = podmiot_dane['nip']
    etree.SubElement(identyfikator, f"{ETD}PelnaNazwa").text = podmiot_dane['pelna_nazwa']

    adres = etree.SubElement(podmiot1, f"{TNS}AdresPodmiotu")
    etree.SubElement(adres, f"{ETD}KodKraju").text = podmiot_dane['kod_kraju']
    etree.SubElement(adres, f"{ETD}Wojewodztwo").text = podmiot_dane['wojewodztwo']
    etree.SubElement(adres, f"{ETD}Powiat").text = podmiot_dane['powiat']
    etree.SubElement(adres, f"{ETD}Gmina").text = podmiot_dane['gmina']
    etree.SubElement(adres, f"{ETD}NrDomu").text = podmiot_dane['nr_domu']
    etree.SubElement(adres, f"{ETD}Miejscowosc").text = podmiot_dane['miejscowosc']
    etree.SubElement(adres, f"{ETD}KodPocztowy").text = podmiot_dane['kod_pocztowy']
    etree.SubElement(adres, f"{ETD}Poczta").text = podmiot_dane['poczta']

    etree.SubElement(root, f"{TNS}NumerRachunku").text = iban
    
    salda = etree.SubElement(root, f"{TNS}Salda")
    etree.SubElement(salda, f"{TNS}SaldoPoczatkowe").text = "{:.2f}".format(paczka_df['Saldo_Poczatkowe'].iloc[0])
    etree.SubElement(salda, f"{TNS}SaldoKoncowe").text = "{:.2f}".format(paczka_df['Saldo_Koncowe'].iloc[0])

    for index, wiersz in paczka_df.iterrows():
        wyciag_wiersz = etree.SubElement(root, f"{TNS}WyciagWiersz", typ="G")
        
        etree.SubElement(wyciag_wiersz, f"{TNS}NumerWiersza").text = str(wiersz['Numer_Wiersza'])
        etree.SubElement(wyciag_wiersz, f"{TNS}DataOperacji").text = str(wiersz['Data_Operacji'])
        etree.SubElement(wyciag_wiersz, f"{TNS}NazwaPodmiotu").text = str(wiersz['Nazwa_Podmiotu'])
        etree.SubElement(wyciag_wiersz, f"{TNS}OpisOperacji").text = str(wiersz['Opis_Operacji'])
        etree.SubElement(wyciag_wiersz, f"{TNS}KwotaOperacji").text = "{:.2f}".format(wiersz['Kwota_Operacji'])
        etree.SubElement(wyciag_wiersz, f"{TNS}SaldoOperacji").text = "{:.2f}".format(wiersz['Saldo_Operacji'])

    sumy = sumy_kontrolne[(iban, okres_yyyymm)]
    
    wyciag_ctrl = etree.SubElement(root, f"{TNS}WyciagCtrl")
    etree.SubElement(wyciag_ctrl, f"{TNS}LiczbaWierszy").text = str(sumy['LiczbaWierszy'])
    etree.SubElement(wyciag_ctrl, f"{TNS}SumaObciazen").text = "{:.2f}".format(sumy['SumaObciazen'])
    etree.SubElement(wyciag_ctrl, f"{TNS}SumaUznan").text = "{:.2f}".format(sumy['SumaUznan'])

    return etree.ElementTree(root)

def uruchom_raport_dla_miesiaca(session: Session, nip_firmy: str, miesiac_yyyymm: str, plik_naglowki: str, plik_pozycje: str):
    print(f"Rozpoczynam generowanie JPK_WB dla okresu: {miesiac_yyyymm}")
    
    try:
        podmiot_dane = db.pobierz_dane_podmiotu(session, nip_firmy)
    except Exception as e:
        print(f"Błąd inicjalizacji: {e}")
        return

    try:
        df_polaczone = _read_input_files(plik_naglowki, plik_pozycje)
    except Exception as e:
        db.zapisz_log_bledu(session, plik_naglowki, "BŁĄD_WCZYTYWANIA", str(e))
        print(f"Przerwano: {e}")
        return

    ibany_w_pliku = set(df_polaczone['IBAN'].unique())
    dozwolone_ibany = {rachunek.numer_iban for rachunek in session.query(db.SlownikRachunkow).all()}
    
    nieznane_ibany = ibany_w_pliku - dozwolone_ibany
    if nieznane_ibany:
        opis = f"Znaleziono niezarejestrowane rachunki: {nieznane_ibany}"
        db.zapisz_log_bledu(session, plik_naglowki, "BŁĄD_IBAN", opis)
        print(f"Przerwano: {opis}")
        return

    try:
        df_zwalidowane, sumy_kontrolne = _validate_sums(df_polaczone)
    except Exception as e:
        db.zapisz_log_bledu(session, plik_pozycje, "BŁĄD_MATEMATYCZNY", str(e))
        print(f"Przerwano: {e}")
        return

    df_miesiac = df_zwalidowane[df_zwalidowane['Okres_YYYYMM'] == miesiac_yyyymm]
    if df_miesiac.empty:
        print(f"Brak danych dla wybranego miesiąca {miesiac_yyyymm}.")
        return

    grupy = df_miesiac.groupby('IBAN')
    sciezka_xsd = XSD_FILES_PATH / 'Schemat_JPK_WB(1)_v1-0.xsd'

    for iban, paczka_df in grupy:
        print(f"Generowanie XML dla rachunku: {iban}")
        drzewo_xml = _generuj_xml_dla_wyciagu(iban, miesiac_yyyymm, paczka_df, sumy_kontrolne, podmiot_dane)
        
        try:
            czy_poprawny = _waliduj_xml_ze_schematem(drzewo_xml, sciezka_xsd)
            if not czy_poprawny:
                db.zapisz_log_bledu(session, f"Wyciąg_{iban}", "BŁĄD_XSD", "Plik nie przeszedł walidacji strukturalnej MF.")
                continue 
        except Exception as e:
            print(f"Błąd krytyczny narzędzia walidacji: {e}")
            continue

        nazwa_pliku = f"JPK_WB_{iban}_{miesiac_yyyymm}.xml"
        drzewo_xml.write(XML_FILES_PATH / nazwa_pliku, pretty_print=True, xml_declaration=True, encoding="UTF-8")
        print(f"Pomyślnie zapisano plik: {nazwa_pliku}\n")

        try:
            _zapisz_wyciag_do_bazy(session, iban, miesiac_yyyymm, paczka_df)
        except Exception as e:
            db.zapisz_log_bledu(session, f"Wyciąg_{iban}", "BŁĄD_BAZY", str(e))
            print(f"Wygenerowano XML, ale błąd zapisu do bazy: {e}")

    print("Zakończono procesowanie wyciągów.")

def _waliduj_xml_ze_schematem(drzewo_xml: etree.ElementTree, sciezka_do_xsd) -> bool:
    try:
        with open(sciezka_do_xsd, 'rb') as plik_xsd:
            xsd_doc = etree.parse(plik_xsd)
            
        schemat = etree.XMLSchema(xsd_doc)
        
    except etree.XMLSchemaParseError as e:
        raise ValueError(f"Błąd podczas wczytywania samego pliku XSD (upewnij się, że plik jest poprawny): {e}")

    czy_poprawny = schemat.validate(drzewo_xml)

    if czy_poprawny:
        print("Plik XML jest zgodny ze schematem.")
        return True
    else:
        print("Błąd walidacji XML. Plik nie jest zgodny ze schematem.")
        print("-" * 50)
        print("SZCZEGÓŁY BŁĘDÓW:")
        
        for blad in schemat.error_log:
            print(f"[Linia {blad.line}, Kolumna {blad.column}]")
            print(f"Komunikat: {blad.message}")
            print("-" * 50)
            
        return False
    
def _zapisz_wyciag_do_bazy(session: Session, iban: str, okres_yyyymm: str, paczka_df: pd.DataFrame):
    istniejacy_wyciag = session.query(db.NaglowekWyciagu).filter_by(numer_iban=iban, okres_yyyymm=okres_yyyymm).first()
    
    if istniejacy_wyciag:
        print(f"Wyciąg dla rachunku {iban} za okres {okres_yyyymm} już istnieje w bazie. Pomijam zapis.")
        return

    pierwszy_wiersz = paczka_df.iloc[0]
    
    nowy_naglowek = db.NaglowekWyciagu(
        numer_iban=iban,
        okres_yyyymm=okres_yyyymm,
        waluta=str(pierwszy_wiersz['Waluta']),
        saldo_poczatkowe=pierwszy_wiersz['Saldo_Poczatkowe'],
        saldo_koncowe=pierwszy_wiersz['Saldo_Koncowe']
    )

    wiersze_db = []
    for index, wiersz in paczka_df.iterrows():
        nowa_operacja = db.WierszOperacji(
            numer_wiersza=int(wiersz['Numer_Wiersza']),
            data_operacji=str(wiersz['Data_Operacji']),
            nazwa_podmiotu=str(wiersz['Nazwa_Podmiotu']),
            opis_operacji=str(wiersz['Opis_Operacji']),
            kwota_operacji=wiersz['Kwota_Operacji'],
            saldo_operacji=wiersz['Saldo_Operacji']
        )
        wiersze_db.append(nowa_operacja)

    nowy_naglowek.wiersze_operacji = wiersze_db

    session.add(nowy_naglowek)
    try:
        session.commit()
        print(f"Pomyślnie zarchiwizowano dane w bazie danych dla rachunku: {iban}")
    except Exception as e:
        session.rollback()
        raise ValueError(f"Błąd podczas zapisu do bazy danych: {e}")