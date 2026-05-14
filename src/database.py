from sqlalchemy import Column, Integer, String, Numeric, Date, ForeignKey, UniqueConstraint, DateTime, Text
from sqlalchemy.orm import DeclarativeBase, relationship, Session
from sqlalchemy.sql import func

class Base(DeclarativeBase):
    pass

class NaglowekWyciagu(Base):
    __tablename__ = 'naglowek_wyciagu'

    id = Column(Integer, primary_key=True, autoincrement=True)
    
    numer_iban = Column(String(30), nullable=False)
    okres_yyyymm = Column(String(6), nullable=False)
    waluta = Column(String(3), nullable=False)
    saldo_poczatkowe = Column(Numeric(15, 2), nullable=False)
    saldo_koncowe = Column(Numeric(15, 2), nullable=False)

    __table_args__ = (
        UniqueConstraint('numer_iban', 'okres_yyyymm', name='uq_iban_okres'),
    )

    wiersze_operacji = relationship("WierszOperacji", back_populates="naglowek", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Naglowek(IBAN='{self.numer_iban}', Okres='{self.okres_yyyymm}')>"


class WierszOperacji(Base):
    __tablename__ = 'wiersz_operacji'

    id = Column(Integer, primary_key=True, autoincrement=True)
    
    naglowek_id = Column(Integer, ForeignKey('naglowek_wyciagu.id'), nullable=False)
    
    numer_wiersza = Column(Integer, nullable=False)
    data_operacji = Column(Date, nullable=False)
    nazwa_podmiotu = Column(String(255), nullable=False)
    opis_operacji = Column(String(255), nullable=False)
    kwota_operacji = Column(Numeric(15, 2), nullable=False)
    saldo_operacji = Column(Numeric(15, 2), nullable=False)

    naglowek = relationship("NaglowekWyciagu", back_populates="wiersze_operacji")

    def __repr__(self):
        return f"<Wiersz(Nr='{self.numer_wiersza}', Kwota='{self.kwota_operacji}')>"

class SlownikRachunkow(Base):
    __tablename__ = 'slownik_rachunkow'

    id = Column(Integer, primary_key=True, autoincrement=True)
    numer_iban = Column(String(30), unique=True, nullable=False)
    
    opis = Column(String(100), nullable=True)

    def __repr__(self):
        return f"<Rachunek(IBAN='{self.numer_iban}')>"


class SlownikPodmiotow(Base):
    __tablename__ = 'slownik_podmiotow'

    id = Column(Integer, primary_key=True, autoincrement=True)
    
    nip = Column(String(15), unique=True, nullable=False)
    pelna_nazwa = Column(String(255), nullable=False)
    regon = Column(String(14), nullable=True)

    kod_kraju = Column(String(2), nullable=False)
    wojewodztwo = Column(String(50), nullable=False)
    powiat = Column(String(50), nullable=False)
    gmina = Column(String(50), nullable=False)
    ulica = Column(String(100), nullable=True)
    nr_domu = Column(String(10), nullable=False)
    nr_lokalu = Column(String(10), nullable=True)
    miejscowosc = Column(String(100), nullable=False)
    kod_pocztowy = Column(String(10), nullable=False)
    poczta = Column(String(100), nullable=False)

    def __repr__(self):
        return f"<Podmiot(NIP='{self.nip}', Nazwa='{self.pelna_nazwa}')>"


class LogImportu(Base):
    __tablename__ = 'log_importu'

    id = Column(Integer, primary_key=True, autoincrement=True)
    data_zdarzenia = Column(DateTime, server_default=func.now(), nullable=False)
    
    plik_zrodlowy = Column(String(255), nullable=True)
    
    typ_bledu = Column(String(50), nullable=False)
    

    opis = Column(Text, nullable=False)

    def __repr__(self):
        return f"<Log(Data='{self.data_zdarzenia}', Typ='{self.typ_bledu}')>"

def pobierz_dane_podmiotu(session: Session, nip_firmy: str) -> dict:
    podmiot = session.query(SlownikPodmiotow).filter_by(nip=nip_firmy).first()
    
    if not podmiot:
        raise ValueError(f"Brak podmiotu o NIP {nip_firmy} w słowniku bazy danych!")
        
    return {
        'nip': podmiot.nip,
        'pelna_nazwa': podmiot.pelna_nazwa,
        'kod_kraju': podmiot.kod_kraju,
        'wojewodztwo': podmiot.wojewodztwo,
        'powiat': podmiot.powiat,
        'gmina': podmiot.gmina,
        'nr_domu': podmiot.nr_domu,
        'miejscowosc': podmiot.miejscowosc,
        'kod_pocztowy': podmiot.kod_pocztowy,
        'poczta': podmiot.poczta,
        'kod_urzedu': '1471'
    }

def zapisz_log_bledu(session: Session, plik: str, typ_bledu: str, opis_bledu: str):
    nowy_log = LogImportu(
        plik_zrodlowy=plik,
        typ_bledu=typ_bledu,
        opis=opis_bledu
    )
    session.add(nowy_log)
    session.commit()