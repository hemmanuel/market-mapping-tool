with open('src/models/relational.py', 'r') as f:
    content = f.read()

content = content.replace(
    '    ontology: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)\n    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))',
    '    ontology: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)\n    graph_status: Mapped[str] = mapped_column(String(50), default="idle")\n    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))'
)

with open('src/models/relational.py', 'w') as f:
    f.write(content)
