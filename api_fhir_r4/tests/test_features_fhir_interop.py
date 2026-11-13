"""
Tests for backend/features/fhir-interop.feature (api_fhir_r4 part).

The CSU program / cheque mapping (#38368, #38406) comes from Y-Note-SAS test-csu. The tests
check the expected output only: the extension URL is checked for "claim-program" and the
cheque identifier by its value.
"""
import unittest
from unittest import mock

from django.test import TestCase

from api_fhir_r4.converters.claimConverter import ClaimConverter
from api_fhir_r4.converters.coverageConverter import CoverageConverter
from api_fhir_r4.tests import CoverageTestMixin
from program.test_helpers import create_test_program

GAP = "CSU FHIR program/cheque mapping (#38368/#38406) is not in this checkout"


def _extension_urls(fhir_obj):
    return [ext.url for ext in (fhir_obj.extension or [])]


class CoverageCsuTest(CoverageTestMixin):
    def _policy(self, cheque="CC240523"):
        policy = self.create_test_imis_instance()
        policy.policy_number = cheque
        policy.product.program = create_test_program(code="CCS", name="Chèque Santé")
        policy.product.save()
        policy.save()
        return policy

    # Scenario: The Coverage exposes the Chèque Santé number as a second identifier (@redmine-38368 @redmine-38406)
    def test_cheque_number_identifier(self):
        fhir = CoverageConverter.to_fhir_obj(self._policy())
        values = [i.value for i in fhir.identifier]
        self.assertIn("CC240523", values, GAP)

    # Scenario: The Coverage lists the funding program as a payor (@redmine-38368 @redmine-38132)
    def test_coverage_program_payor(self):
        policy = self._policy()
        fhir = CoverageConverter.to_fhir_obj(policy)
        payors = [p.reference for p in fhir.payor or []]
        self.assertIn(f"Organization/program-{policy.product.program.idProgram}", payors, payors)

    # Scenario: The Coverage effective date is optional (@redmine-38368)
    def test_coverage_without_effective_date(self):
        policy = self._policy()
        policy.effective_date = None
        try:
            fhir = CoverageConverter.to_fhir_obj(policy)
        except AttributeError as exc:
            self.fail(f"{GAP}: conversion fails without effective date ({exc})")
        self.assertIsNotNone(fhir)


class ClaimCsuTest(TestCase):
    # Scenario: The Claim carries the funding program in an extension (@redmine-38368)
    def test_claim_program_extension(self):
        from claim.test_helpers import create_test_claim
        from core.test_helpers import create_security_tree
        from insuree.test_helpers import create_test_insuree
        from medical.models import Diagnosis
        from medical.test_helpers import create_test_diagnosis
        tree = create_security_tree("FFHC")
        icd = Diagnosis.objects.filter(validity_to__isnull=True).first() or create_test_diagnosis({"code": "FFHCD"})
        insuree = create_test_insuree(custom_props={"current_village": tree.v1},
                                      family_custom_props={"location": tree.v1})
        from claim.test_helpers import create_test_claim_admin
        admin = create_test_claim_admin(custom_props={"code": "FFHCCA", "health_facility_id": tree.hf1.id})
        claim = create_test_claim(custom_props={
            "code": "FFHC-1", "health_facility_id": tree.hf1.id, "insuree_id": insuree.id, "icd_id": icd.id,
            "admin_id": admin.id, "visit_type": "O",
            "program": create_test_program(code="CCS", name="Chèque Santé")})
        fhir = ClaimConverter.to_fhir_obj(claim)
        self.assertTrue(any("claim-program" in url for url in _extension_urls(fhir)), GAP)


class PatientFamilyTest(TestCase):
    # Scenario: A family is created for a head patient created through FHIR (@redmine-33428)
    def test_head_patient_gets_family(self):
        from api_fhir_r4.serializers.patientSerializer import PatientSerializer
        from insuree.test_helpers import create_test_insuree
        insuree = create_test_insuree(with_family=False, custom_props={"chf_id": "FHIRFAM01"})
        self.assertIsNone(insuree.family)
        request = mock.Mock()
        serializer = PatientSerializer(context={"request": request})
        with mock.patch("api_fhir_r4.serializers.patientSerializer.InsureeService") as service:
            service.return_value.create_or_update.return_value = insuree
            serializer.create({"chf_id": "FHIRFAM02", "head": True, "audit_user_id": -1})
        insuree.refresh_from_db()
        self.assertIsNotNone(insuree.family)
        self.assertEqual(insuree.family.head_insuree_id, insuree.id)


class ClaimSubItemsTest(TestCase):
    # Scenario: FHIR claim creation with sub-services and sub-items (@redmine-38407)
    @unittest.skip("open: #38407")
    def test_sub_services_and_items(self):
        pass
