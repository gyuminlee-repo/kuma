from sidecar_kuro.models import (
    AlternativesResultModel,
    DesignResultResponseModel,
    PolymeraseProfileModel,
    SdmPrimerResultModel,
    WorkspaceInputsModel,
    WorkspaceResultsModel,
    WorkspaceSettingsModel,
    WorkspaceUiModel,
    WorkspaceV2Data,
)


def test_to_rpc_dict_excludes_none_optionals():
    primer = SdmPrimerResultModel(
        mutation="Q1W",
        aa_position=1,
        codon_pos=0,
        forward_seq="ATGC",
        reverse_seq="GCAT",
        fwd_len=4,
        rev_len=4,
        overlap_len=2,
        tm_no_fwd=60.0,
        tm_no_rev=59.0,
        tm_overlap=40.0,
        tm_condition_met=True,
        tolerance_used=1.0,
        has_offtarget=False,
        penalty=0.0,
        gc_fwd=50.0,
        gc_rev=50.0,
        wt_codon="CAA",
        mt_codon="TGG",
        overlap_seq="TG",
        warnings=[],
    )

    dumped = primer.to_rpc_dict()

    assert "candidate_count" not in dumped
    assert "tolerance_fwd" not in dumped
    assert "offtarget_fwd" not in dumped
    assert dumped["has_offtarget"] is False
    assert dumped["penalty"] == 0.0


def test_nested_rpc_models_also_drop_none_fields():
    result = DesignResultResponseModel(
        results=[],
        success_count=0,
        total_count=0,
        failed_mutations=[],
    ).to_rpc_dict()

    assert "rescue_stats" not in result
    assert "rescued_mutations" not in result
    assert "cancelled" not in result

    alternatives = AlternativesResultModel(candidates=[]).to_rpc_dict()

    assert "mutation" not in alternatives
    assert "count" not in alternatives


def test_polymerase_profile_to_rpc_dict_excludes_none_optionals():
    profile = PolymeraseProfileModel(
        name="Q5",
        tm_method="santalucia",
        salt_correction="owczarzy",
        opt_tm=62.0,
        min_tm=58.0,
        max_tm=68.0,
        opt_size=30,
        min_size=18,
        max_size=45,
        min_gc=40.0,
        max_gc=60.0,
        salt_monovalent=50.0,
        salt_divalent=1.5,
        dntp_conc=0.2,
        dna_conc=250.0,
        max_tm_diff=5.0,
    ).to_rpc_dict()

    assert "opt_tm_fwd" not in profile
    assert "opt_tm_rev" not in profile
    assert "overlap_len" not in profile
    assert profile["name"] == "Q5"


def test_workspace_v2_to_rpc_dict_excludes_none_nested_optionals():
    workspace = WorkspaceV2Data(
        version=2,
        inputs=WorkspaceInputsModel(
            fastaPath="sample.fa",
            mutationInputMode="text",
            mutationText="Q1W",
            evolveproCsvPath="",
            selectedGene="0",
        ),
        settings=WorkspaceSettingsModel(
            codonStrategy="closest",
            maxPrimers=96,
            tmFwdTarget=62.0,
            tmRevTarget=58.0,
            tmOverlapTarget=42.0,
            gcMin=40.0,
            gcMax=60.0,
        ),
        results=WorkspaceResultsModel(
            designResults=[],
            successCount=0,
            totalCount=0,
            failedMutations=[],
            plateMappings=[],
            dedupInfo={},
            manuallySwapped={},
            customCandidates={},
        ),
        ui=WorkspaceUiModel(tableSorting=[]),
    ).to_rpc_dict()

    assert "cache" not in workspace
    assert "selectedPolymerase" not in workspace["settings"]
    assert "uniprotAccession" not in workspace["settings"]
    assert workspace["version"] == 2


