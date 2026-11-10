from app.models_extended import RateCounter
from app.database import Base,make_engine
from app.rate_limit import consume
from sqlalchemy.orm import Session


def test_limit_is_shared_between_connections(tmp_path):
    engine=make_engine(f'sqlite:///{tmp_path / "limits.db"}')
    Base.metadata.create_all(engine)
    with Session(engine) as first,Session(engine) as second:
        assert consume(first,'same-client',2,120)
        assert consume(second,'same-client',2,120)
        assert not consume(first,'same-client',2,120)
        assert consume(second,'same-client',2,180)
    engine.dispose()
