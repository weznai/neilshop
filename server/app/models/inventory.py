"""库存与供应链域（5 表）"""

from sqlalchemy import BigInteger, Column, DateTime, Index, Integer, SmallInteger, String

from app.core.db import Base, utcnow


class StockMovement(Base):
    __tablename__ = "stock_movements"
    __table_args__ = (
        Index("idx_variant_time", "variant_id", "created_at"),
        Index("idx_type_time", "type", "created_at"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    variant_id = Column(BigInteger, nullable=False)
    change = Column(Integer, nullable=False)      # 正入负出
    stock_after = Column(Integer, nullable=False)
    type = Column(SmallInteger, nullable=False)
    # 1采购 2预扣 3实扣 4释放 5退货回补 6盘点 7手工 8损耗
    ref_type = Column(String(20))                 # order/purchase/count/rma
    ref_id = Column(BigInteger)
    operator = Column(String(30))
    created_at = Column(DateTime, nullable=False, default=utcnow)


class Supplier(Base):
    __tablename__ = "suppliers"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    contact = Column(String(200))
    lead_time_days = Column(SmallInteger, nullable=False, default=14)
    moq = Column(Integer, nullable=False, default=100)
    notes = Column(String(500))


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    po_no = Column(String(14), nullable=False, unique=True)
    supplier_id = Column(BigInteger, nullable=False)
    status = Column(SmallInteger, nullable=False, default=0)  # 0草稿 1已下单 2部分到货 3全部到货 4取消
    expected_at = Column(DateTime)
    received_at = Column(DateTime)
    total_cost = Column(Integer)
    created_by = Column(BigInteger)
    created_at = Column(DateTime, nullable=False, default=utcnow)


class PurchaseOrderItem(Base):
    __tablename__ = "purchase_order_items"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    po_id = Column(BigInteger, nullable=False, index=True)
    variant_id = Column(BigInteger, nullable=False)
    qty = Column(Integer, nullable=False)
    received_qty = Column(Integer, nullable=False, default=0)
    unit_cost = Column(Integer, nullable=False)


class StockCount(Base):
    __tablename__ = "stock_counts"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    variant_id = Column(BigInteger, nullable=False, index=True)
    expected_qty = Column(Integer, nullable=False)
    counted_qty = Column(Integer, nullable=False)
    diff = Column(Integer, nullable=False)
    counted_by = Column(BigInteger, nullable=False)
    created_at = Column(DateTime, nullable=False, default=utcnow)
