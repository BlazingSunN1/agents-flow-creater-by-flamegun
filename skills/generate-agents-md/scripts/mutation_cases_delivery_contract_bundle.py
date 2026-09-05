from __future__ import annotations


DELIVERY_CONTRACT_BUNDLE_MUTANT_CASES = (
    (
        "gate-receipt-schema-v2-check-disabled",
        "scripts/validate_delivery_contract.py",
        'receipt.get("schema_version") != 2',
        'receipt.get("schema_version") not in {1, 2}',
        "scripts.test_validate_delivery_contract.DeliveryContractValidatorTests.test_legacy_gate_receipt_schema_is_rejected",
    ),
    (
        "gate-receipt-argv-binding-disabled",
        "scripts/validate_delivery_contract.py",
        "if argv != expected_argv or argv_sha != observed_argv_sha:",
        "if False:",
        "scripts.test_validate_delivery_contract.DeliveryContractValidatorTests.test_gate_receipt_binds_registered_argv_exit_code_and_time",
    ),
    (
        "delivery-configuration-workset-binding-disabled",
        "scripts/delivery_contract_bundle_validation.py",
        '        "configuration_files": _split_paths(context.get("Configuration files", "")),\n',
        "",
        "scripts.test_validate_delivery_bundle.DeliveryBundleValidatorTests.test_delivery_contract_configuration_files_must_match_context",
    ),
    (
        "delivery-input-workset-binding-disabled",
        "scripts/delivery_contract_bundle_validation.py",
        '        "input_files": _split_paths(context.get("Input files", "")),\n',
        "",
        "scripts.test_validate_delivery_bundle.DeliveryBundleValidatorTests.test_delivery_contract_input_files_must_match_context",
    ),
    (
        "delivery-dependency-boundary-binding-disabled",
        "scripts/delivery_contract_bundle_validation.py",
        '        "direct_dependency_boundaries": context.get("Direct dependency boundaries"),\n',
        "",
        "scripts.test_validate_delivery_bundle.DeliveryBundleValidatorTests.test_delivery_contract_dependency_boundaries_must_match_context",
    ),
)
