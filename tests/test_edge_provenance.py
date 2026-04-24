from codegraph.output.edge_provenance import edge_provenance


def test_edge_provenance_bands():
    assert edge_provenance(1.0) == "EXTRACTED"
    assert edge_provenance(0.85) == "EXTRACTED"
    assert edge_provenance(0.84) == "INFERRED"
    assert edge_provenance(0.35) == "INFERRED"
    assert edge_provenance(0.34) == "AMBIGUOUS"
    assert edge_provenance(0.2) == "AMBIGUOUS"
