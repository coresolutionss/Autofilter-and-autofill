import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import os
os.environ['EXTRACTION_PROVIDER'] = 'local'  # Unit/UI tests never upload documents.
import sys
from unittest.mock import patch
import zipfile

from PIL import Image, ImageDraw
from streamlit.testing.v1 import AppTest

import application_store as store
from form_config import FORMS, field_labels
from intake_extraction import extract_document, labeled_fields, mexican_fields, mrz_fields, read_image, validate_upload
from license_front_reader import us_front_fields, read_us_license_front, painted_regions, overlaps_paint
from photo_preprocessing import straighten_card, crop_photo
import reader_runtime


def attachment(kind="id_card", subject="Owner"):
    buffer = io.BytesIO()
    image = Image.new("RGB", (800, 600), "white")
    ImageDraw.Draw(image).text((10, 10), kind + " / " + subject, fill="black")
    image.save(buffer, format="PNG")
    data = buffer.getvalue()
    return {"id": "sample-" + kind, "name": "sample.png", "data": data,
        "sha256": hashlib.sha256(data).hexdigest(), "kind": kind, "subject": subject,
        "country": "Sample", "reviewed": True, "manual_reason": "Checked synthetic source manually",
        "rotation": 0, "enhance": True, "languages": ["eng"],
        "extraction": {"fields": {}, "method": "manual", "messages": []}}


class IntakeTests(unittest.TestCase):
    def test_reader_runtime_reloads_same_size_source_and_stale_imports(self):
        name = "temporary_intake_reader"
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / (name + ".py")
            path.write_text("def value(): return 'old'\n", encoding="utf-8")
            timestamp = path.stat().st_mtime
            try:
                with patch.object(sys, "path", [folder, *sys.path]), patch.object(reader_runtime, "ROOT", Path(folder)), \
                    patch.object(reader_runtime, "READER_MODULES", (name,)), patch.object(reader_runtime, "_loaded_sources", {}):
                    first_build = reader_runtime.refresh_readers()
                    self.assertEqual(sys.modules[name].value(), "old")
                    path.write_text("def value(): return 'new'\n", encoding="utf-8")
                    os.utime(path, (timestamp, timestamp))
                    second_build = reader_runtime.refresh_readers()
                    self.assertNotEqual(first_build, second_build)
                    self.assertEqual(sys.modules[name].value(), "new")
            finally:
                sys.modules.pop(name, None)
    def test_schemas_have_unique_fields(self):
        for name, config in FORMS.items():
            keys = [key for _, fields in config["sections"] for key, _ in fields]
            self.assertEqual(len(keys), len(set(keys)))
            self.assertTrue(set(config["required"]).issubset(keys))

    def test_label_extraction_rejects_ambiguous_names(self):
        fields = labeled_fields("Surname: DOE\nSurname: SMITH\nGiven names: JANE")
        self.assertNotIn("last_name", fields)
        self.assertEqual(fields["first_name"], "JANE")
        self.assertEqual(labeled_fields("Company name: Example LLC\nEIN: 12-3456789", tax=True)["tax_id"], "12-3456789")

    def test_valid_international_passport_and_failed_checksum(self):
        text = "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<\nL898902C36UTO7408122F1204159ZE184226B<<<<<10"
        fields, message = mrz_fields(text, "passport")
        self.assertEqual(fields["last_name"], "ERIKSSON")
        self.assertEqual(fields["passport_number"], "L898902C3")
        self.assertEqual(fields["date_of_birth"], "740812")
        fields, message = mrz_fields(text.replace("L898902C36", "L898902C37"), "passport")
        self.assertEqual(fields, {})
        self.assertIn("failed", message)
        td1 = "I<UTOD231458907<<<<<<<<<<<<<<<\n7408122F1204159UTO<<<<<<<<<<<6\nERIKSSON<<ANNA<MARIA<<<<<<<<<<<"
        fields, message = mrz_fields(td1, "id_card")
        self.assertEqual(fields["id_number"], "D23145890")

    def test_mexican_rfc_and_ine_name_are_not_guessed(self):
        tax = mexican_fields("RFC: ABC010203AB1\nDenominación/Razón Social: EJEMPLO SA DE CV", tax=True)
        self.assertEqual(tax["tax_id"], "ABC010203AB1")
        self.assertEqual(tax["company_name"], "EJEMPLO SA DE CV")
        ine = mexican_fields("NOMBRE\nGARCÍA\nLÓPEZ\nANA MARÍA\nDOMICILIO\nCALLE EJEMPLO 123\nCENTRO 06000\nCIUDAD DE MÉXICO\nCLAVE DE ELECTOR ABC123\nCURP: SAMPLE")
        self.assertEqual(ine["full_name"], "GARCÍA LÓPEZ ANA MARÍA")
        self.assertNotIn("first_name", ine)
        self.assertIn("CALLE EJEMPLO", ine["street_address"])
        self.assertEqual(ine["elector_key"], "ABC123")
        with patch("intake_extraction.pytesseract.image_to_string", return_value="RFC: ABCO10203AB1"):
            result = extract_document(attachment()["data"], "tax_document")
        self.assertNotIn("tax_id", result["fields"])

    def test_ocr_unavailable_allows_manual_entry(self):
        doc = attachment()
        with patch("intake_extraction.pytesseract.image_to_string", side_effect=RuntimeError("timeout")):
            result = extract_document(doc["data"], "id_card")
        self.assertEqual(result["fields"], {})
        self.assertTrue(any("manually" in m for m in result["messages"]))

    def test_mislabeled_upload_rejected(self):
        with self.assertRaises(ValueError):
            validate_upload(attachment()["data"], "false.pdf")

    def test_us_license_front_names_address_and_dates(self):
        text = "DL I1234568 CLASS C\nEXP 08/31/2014\nLNCARDHOLDER\nFNIMA |\n2570 24TH STREET\nANYTOWN, CA 95818\nDOB 08/31/1977"
        fields, _ = us_front_fields(text, california=True)
        self.assertEqual(fields["first_name"], "IMA")
        self.assertEqual(fields["last_name"], "CARDHOLDER")
        self.assertEqual(fields["license_number"], "I1234568")
        self.assertEqual(fields["date_of_birth"], "1977-08-31")
        self.assertEqual(fields["street_address"], "2570 24TH STREET")
        self.assertEqual(fields["zip_code"], "95818")
        fields, messages = us_front_fields(text.replace("DL I1234568", "0 11234568").replace("DOB ", "pos "), california=True)
        self.assertNotIn("license_number", fields)
        self.assertEqual(fields["date_of_birth"], "1977-08-31")
        self.assertTrue(any("manual confirmation" in m for m in messages))
        mixed, _ = us_front_fields("LN García López\nFN María José")
        self.assertEqual(mixed["first_name"], "María José")
        self.assertEqual(mixed["last_name"], "García López")

    def test_camera_card_boundary_and_perspective(self):
        image = Image.new("RGB", (900, 650), "#777777")
        draw = ImageDraw.Draw(image)
        draw.polygon([(200, 80), (780, 155), (710, 525), (125, 430)], fill="#eeeeee", outline="black", width=5)
        corrected, detected = straighten_card(image)
        self.assertTrue(detected)
        self.assertLess(corrected.width, image.width)
        self.assertTrue(1.3 < corrected.width / corrected.height < 2.1)
        untouched, detected = straighten_card(Image.new("RGB", (600, 400), "white"))
        self.assertFalse(detected)
        self.assertEqual(untouched.size, (600, 400))

    def test_photo_crop_validation_and_review_fingerprint(self):
        image = Image.new("RGB", (1000, 800), "white")
        crop = {"horizontal": [20, 80], "vertical": [25, 75]}
        self.assertEqual(crop_photo(image, crop).size, (600, 400))
        self.assertEqual(image.size, (1000, 800))
        with self.assertRaises(ValueError):
            crop_photo(image, {"horizontal": [80, 20], "vertical": [0, 100]})
        doc = attachment()
        before = store.fingerprint("new_account", {}, [doc], "Staff", "")
        doc["crop"] = crop
        self.assertNotEqual(before, store.fingerprint("new_account", {}, [doc], "Staff", ""))

    def test_street_can_be_read_without_a_city(self):
        fields, _ = us_front_fields("123 SAMPLE STREET APT 4\n[covered city]", california=True)
        self.assertEqual(fields["street_address"], "123 SAMPLE STREET APT 4")
        self.assertNotIn("city", fields)

    def test_white_patch_detection_does_not_treat_white_card_as_redacted(self):
        image = Image.new("RGB", (600, 360), "#bbccaa")
        ImageDraw.Draw(image).rectangle((230, 100, 340, 115), fill="white")
        regions = painted_regions(image)
        self.assertTrue(overlaps_paint((220, 95, 360, 120), regions))
        self.assertFalse(overlaps_paint((220, 200, 360, 220), regions))
        self.assertEqual(painted_regions(Image.new("RGB", (600, 360), "white")), [])

    def test_small_labelled_fields_replace_noisy_full_card_reads_and_block_covered_names(self):
        image = Image.new("RGB", (600, 360), "#bbccaa")
        with patch("license_front_reader._read_legacy_california_front", return_value=({}, [])), \
             patch("license_front_reader.pytesseract.image_to_string", return_value="California DRIVER LICENSE\nLN WRONG\nDOB 01/02/1980"), \
             patch("license_front_reader.labelled_card_rows", return_value=({"date_of_birth": "2000-01-02", "street_address": "123 SAMPLE STREET"}, {"last_name"}, ["Covered name left blank"])):
            fields, _ = read_us_license_front(image)
        self.assertEqual(fields["date_of_birth"], "2000-01-02")
        self.assertEqual(fields["street_address"], "123 SAMPLE STREET")
        self.assertNotIn("last_name", fields)

    def test_license_front_disagreement_is_not_autofilled(self):
        with patch("license_front_reader.pytesseract.image_to_string", side_effect=["LNDOE\nFNJANE", "LNROE\nFNJANE"] * 3):
            fields, messages = read_us_license_front(Image.new("RGB", (600, 385)), "California DRIVER LICENSE\nLNDOE")
        self.assertEqual(fields["first_name"], "JANE")
        self.assertNotIn("last_name", fields)
        self.assertTrue(any("disagree" in m or "uncertain" in m for m in messages))

    def test_save_load_export_preserves_originals_and_unicode(self):
        fields = {"company_name": "Société Example", "first_name": "Jane", "last_name": "Doe", "tax_id": "12-3456789"}
        documents = [attachment(), attachment("tax_document", "Business")]
        with tempfile.TemporaryDirectory() as root:
            record = store.save_application("new_account", fields, documents, "Reviewer", "Test", "reviewed", root=root)
            loaded, originals = store.load_application(record["id"], root=root)
            self.assertEqual(loaded["fields"]["company_name"], fields["company_name"])
            self.assertEqual(originals[0]["data"], documents[0]["data"])
            archive = zipfile.ZipFile(io.BytesIO(store.export_bundle(record["id"], root=root)))
            self.assertEqual(len(archive.namelist()), 6)
            self.assertIn("application-form.pdf", archive.namelist())
            self.assertIn("report.html", archive.namelist())
            self.assertEqual(len(store.list_applications(root)), 1)
            saved_file = Path(root) / record["id"] / "documents" / record["documents"][0]["stored_name"]
            saved_file.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "checksum"):
                store.load_application(record["id"], root=root)

    def test_failed_save_is_atomic(self):
        with tempfile.TemporaryDirectory() as root:
            with patch("application_store.report_html", side_effect=OSError("disk failure")):
                with self.assertRaises(OSError):
                    store.save_application("new_account", {}, [attachment()], root=root)
            self.assertEqual(list(Path(root).iterdir()), [])

    def test_final_validation_and_new_address_separation(self):
        fields = {"account_number": "123", "first_name": "Jane", "last_name": "Doe", "change_reason": "Moved",
                  "old_physical_address": "A", "new_physical_address": "A"}
        self.assertTrue(store.validation_errors("information_change", fields, [], "Staff"))
        fields["new_shipping_address"] = "B"
        self.assertEqual(store.validation_errors("information_change", fields, [], "Staff"), [])
        self.assertTrue(store.validation_errors("new_account", {}, [], ""))
        doc = attachment()
        before = store.fingerprint("new_account", {}, [doc], "Staff", "")
        doc["reviewed"] = False
        self.assertNotEqual(before, store.fingerprint("new_account", {}, [doc], "Staff", ""))

    def test_report_escaping_csv_and_path_safety(self):
        record = store.build_record("new_account", {"company_name": "<script>alert(1)</script>", "first_name": "=SUM(1,2)"}, [], "", "", "draft")
        self.assertNotIn("<script>", store.report_html(record))
        self.assertIn("&lt;script&gt;", store.report_html(record))
        self.assertIn("'=SUM", store.csv_report(record).decode("utf-8-sig"))
        with self.assertRaises(ValueError):
            store.safe_record_dir("../outside")


class StoredFormField:
    """Inspect PDF form backing state; browser checks cover component inputs."""
    def __init__(self, app, key):
        self.app, self.key = app, key
    @property
    def value(self):
        return self.app.session_state[self.key]
    def set_value(self, value):
        self.app.session_state[self.key] = value
        return self
    def run(self):
        return self.app.run()


class AppWorkflowTests(unittest.TestCase):
    def run_app(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
        self.assertEqual(list(app.exception), [])
        return app

    @staticmethod
    def field_by_key(app, key):
        return StoredFormField(app, key)

    @staticmethod
    def input_by_label(app, label):
        native = next((x for x in app.text_input if x.label == label), None)
        if native is not None:
            return native
        form_type = app.selectbox(key="form_type").value
        work = app.session_state["workspaces"][form_type]
        field = next(key for key, text in field_labels(form_type).items() if text == label.rstrip(" *"))
        return StoredFormField(app, f"field:{work['id']}:{field}")

    @staticmethod
    def button_by_label(app, label):
        return next(x for x in app.button if x.label == label)

    def test_both_forms_preserve_unsaved_values(self):
        app = self.run_app()
        self.input_by_label(app, "Company legal name *").set_value("Example LLC").run()
        app.selectbox(key="form_type").set_value("information_change").run()
        self.assertEqual(list(app.exception), [])
        self.input_by_label(app, "Current account number *").set_value("A123").run()
        app.selectbox(key="form_type").set_value("new_account").run()
        self.assertEqual(self.input_by_label(app, "Company legal name *").value, "Example LLC")
        self.assertEqual(list(app.exception), [])

    def test_app_refreshes_an_old_runtime_dependency_list(self):
        app = self.run_app()
        self.input_by_label(app, "Company legal name *").set_value("Keep existing work").run()
        previous_modules = reader_runtime.READER_MODULES
        try:
            reader_runtime.READER_MODULES = tuple(name for name in previous_modules if name != "photo_preprocessing")
            reader_runtime._app_loaded_digest = "old runtime"
            app.run()
            self.assertEqual(list(app.exception), [])
            self.assertIn("photo_preprocessing", reader_runtime.READER_MODULES)
            self.assertEqual(self.input_by_label(app, "Company legal name *").value, "Keep existing work")
        finally:
            reader_runtime.READER_MODULES = previous_modules

    def test_change_save_review_and_invalidate_confirmation(self):
        with tempfile.TemporaryDirectory() as root, patch.object(store, "RECORDS_DIR", Path(root)):
            app = self.run_app()
            app.selectbox(key="form_type").set_value("information_change").run()
            for label, value in [("Current account number *", "A123"), ("Owner given names *", "Jane"),
                ("Owner surname *", "Doe"), ("Reason / description of change *", "Relocation"), ("Staff reviewer name", "Staff")]:
                self.input_by_label(app, label).set_value(value)
            work = app.session_state["workspaces"]["information_change"]
            self.field_by_key(app, f"field:{work['id']}:new_shipping_address").set_value("123 New Road").run()
            confirm = next(x for x in app.checkbox if x.label.startswith("I compared"))
            confirm.check().run()
            self.assertFalse(self.button_by_label(app, "Save reviewed application").disabled)
            self.button_by_label(app, "Save reviewed application").click().run()
            self.assertEqual(list(app.exception), [])
            self.assertEqual(store.list_applications(root)[0]["status"], "reviewed")
            self.input_by_label(app, "Owner surname *").set_value("Changed").run()
            self.assertFalse(next(x for x in app.checkbox if x.label.startswith("I compared")).value)
            self.assertTrue(self.button_by_label(app, "Save reviewed application").disabled)
            self.assertTrue(any("unsaved changes" in x.value for x in app.warning))

    def test_document_suggestions_and_manual_review_render(self):
        app = self.run_app()
        work = app.session_state["workspaces"]["new_account"]
        doc = attachment()
        doc["extraction"]["fields"] = {"first_name": "Jane", "street_address": "Home street"}
        work["documents"].append(doc)
        app.run()
        self.assertEqual(list(app.exception), [])
        result = dict(work["documents"][0]["extraction"])
        with patch("intake_extraction.extract_document", return_value=result):
            self.button_by_label(app, "Extract / retry").click().run()
        self.assertEqual(list(app.exception), [])
        self.assertEqual(self.input_by_label(app, "Owner given names *").value, "Jane")
        self.assertEqual(self.field_by_key(app, f"field:{work['id']}:home_address").value, "Home street")
        self.assertEqual(self.field_by_key(app, f"field:{work['id']}:business_address").value, "")

    def test_account_save_and_reopen_keeps_document_associations(self):
        with tempfile.TemporaryDirectory() as root, patch.object(store, "RECORDS_DIR", Path(root)):
            app = self.run_app()
            work = app.session_state["workspaces"]["new_account"]
            work["documents"] = [attachment(), attachment("tax_document", "Business")]
            for key, value in {"company_name": "Example", "first_name": "Jane", "last_name": "Doe", "tax_id": "12-3456789"}.items():
                self.field_by_key(app, f"field:{work['id']}:{key}").set_value(value)
            self.input_by_label(app, "Staff reviewer name").set_value("Staff").run()
            next(x for x in app.checkbox if x.label.startswith("I compared")).check().run()
            self.button_by_label(app, "Save reviewed application").click().run()
            self.assertEqual(list(app.exception), [])
            record_id = store.list_applications(root)[0]["id"]
            app.selectbox(key="form_type").set_value("information_change").run()
            next(x for x in app.checkbox if x.label.startswith("Replace the current")).check().run()
            self.button_by_label(app, "Open saved snapshot").click().run()
            self.assertEqual(list(app.exception), [])
            self.assertEqual(app.selectbox(key="form_type").value, "new_account")
            loaded = app.session_state["workspaces"]["new_account"]
            self.assertEqual([d["kind"] for d in loaded["documents"]], ["id_card", "tax_document"])
            self.assertEqual(self.input_by_label(app, "Owner given names *").value, "Jane")
            self.assertEqual(len(store.load_application(record_id, root)[1]), 2)

    def test_conflicting_sources_never_autofill(self):
        app = self.run_app()
        work = app.session_state["workspaces"]["new_account"]
        one, two = attachment(), attachment("passport")
        one["extraction"]["fields"] = {"first_name": "Jane", "last_name": "Doe"}
        two["extraction"]["fields"] = {"first_name": "Janet", "last_name": "Doe"}
        work["documents"] = [one, two]
        app.run()
        result = dict(work["documents"][0]["extraction"])
        with patch("intake_extraction.extract_document", return_value=result):
            self.button_by_label(app, "Extract / retry").click().run()
        self.assertEqual(list(app.exception), [])
        self.assertEqual(self.input_by_label(app, "Owner given names *").value, "")
        self.assertEqual(self.input_by_label(app, "Owner surname *").value, "Doe")
        self.input_by_label(app, "Owner surname *").set_value("Manual surname").run()
        result = dict(work["documents"][0]["extraction"])
        with patch("intake_extraction.extract_document", return_value=result):
            self.button_by_label(app, "Extract / retry").click().run()
        self.assertEqual(self.input_by_label(app, "Owner surname *").value, "Manual surname")

    def test_retry_analyzes_and_autofills_empty_review_fields(self):
        app = self.run_app()
        work = app.session_state["workspaces"]["new_account"]
        work["documents"] = [attachment("drivers_license")]
        self.field_by_key(app, f"field:{work['id']}:license_number").set_value("MANUALLY-CHECKED").run()
        result = {"fields": {"first_name": "IMA", "last_name": "CARDHOLDER", "license_number": "OTHER",
            "street_address": "2570 24TH STREET"}, "messages": ["Suggestions only"], "method": "test"}
        with patch("intake_extraction.extract_document", return_value=result):
            self.button_by_label(app, "Extract / retry").click().run()
        self.assertEqual(list(app.exception), [])
        self.assertEqual(self.input_by_label(app, "Owner given names *").value, "IMA")
        self.assertEqual(self.field_by_key(app, f"field:{work['id']}:home_address").value, "2570 24TH STREET")
        self.assertEqual(self.field_by_key(app, f"field:{work['id']}:license_number").value, "MANUALLY-CHECKED")
        self.assertFalse(work["documents"][0]["reviewed"])

    def test_groq_requires_explicit_retry_and_passes_provider(self):
        with patch.dict(os.environ, {"EXTRACTION_PROVIDER": "groq"}):
            app = self.run_app()
            work = app.session_state["workspaces"]["new_account"]
            doc = attachment("drivers_license")
            doc["extraction"] = {"fields": {}, "messages": [], "method": "local OCR", "reader_build": "old"}
            work["documents"] = [doc]
            result = {"fields": {"first_name": "JANE"}, "messages": ["Compare original"], "method": "Groq vision / test"}
            with patch("intake_extraction.extract_document", return_value=result) as extract:
                app.run()
                extract.assert_not_called()
                self.button_by_label(app, "Extract / retry").click().run()
                self.assertEqual(extract.call_args.kwargs["provider"], "groq")
                self.assertEqual(extract.call_count, 1)
            self.assertEqual(list(app.exception), [])
            self.assertEqual(self.input_by_label(app, "Owner given names *").value, "JANE")

    def test_old_mrz_failure_is_refreshed_without_losing_entered_fields(self):
        app = self.run_app()
        work = app.session_state["workspaces"]["new_account"]
        doc = attachment("drivers_license")
        doc["extraction"] = {"fields": {}, "messages": ["MRZ check digits failed"], "method": "local OCR / MRZ / barcode"}
        work["documents"] = [doc]
        self.input_by_label(app, "Company legal name *").set_value("Keep staff entry")
        result = {"fields": {"first_name": "IMA", "last_name": "CARDHOLDER"}, "messages": ["License-front OCR suggestions"], "method": "local OCR"}
        with patch("intake_extraction.extract_document", return_value=result) as extract:
            app.run()
        self.assertEqual(list(app.exception), [])
        self.assertEqual(extract.call_count, 1)
        self.assertEqual(self.input_by_label(app, "Company legal name *").value, "Keep staff entry")
        self.assertEqual(self.input_by_label(app, "Owner given names *").value, "IMA")
        self.assertNotIn("MRZ check digits failed", doc["extraction"]["messages"])
        self.assertEqual(doc["extraction"]["reader_build"], reader_runtime.refresh_readers())
        self.assertFalse(doc["reviewed"])
        app.run()
        self.assertEqual(doc["extraction"]["messages"], ["License-front OCR suggestions"])

    def test_review_removes_auxiliary_sections_and_keeps_one_continue(self):
        app = self.run_app()
        self.assertEqual(list(app.exception), [])
        expander_labels = [item.label for item in app.expander]
        self.assertNotIn("Document suggestions and conflicts", expander_labels)
        self.assertNotIn("Additional document details and accessible field editor", expander_labels)
        self.assertEqual(sum(button.label == "Continue to Save & report" for button in app.button), 1)
        self.assertTrue(any("Original document for comparison" in item.value for item in app.markdown))

    def test_add_only_new_file_when_category_changes_with_old_upload_selected(self):
        license_file = io.BytesIO(attachment("drivers_license")["data"])
        license_file.name = "license.png"
        passport_file = io.BytesIO(attachment("passport")["data"])
        passport_file.name = "passport.png"
        with patch("streamlit.file_uploader", return_value=[license_file]):
            app = self.run_app()
            work = app.session_state["workspaces"]["new_account"]
            app.checkbox(key="analyze-on-add:" + work["id"]).uncheck().run()
            self.button_by_label(app, "Add documents to application").click().run()
        self.assertEqual(len(work["documents"]), 1)
        first_id = work["documents"][0]["id"]
        with patch("streamlit.file_uploader", return_value=[license_file, passport_file]):
            app.selectbox(key="kind:" + work["id"]).select("passport").run()
            self.button_by_label(app, "Add documents to application").click().run()
            self.button_by_label(app, "Add documents to application").click().run()
        self.assertEqual(list(app.exception), [])
        self.assertEqual([d["kind"] for d in work["documents"]], ["drivers_license", "passport"])
        self.assertEqual(work["documents"][0]["id"], first_id)
        self.assertEqual(len([item for item in app.expander if "license.png" in item.label]), 1)

    def test_existing_duplicate_sections_are_collapsed_without_changing_fields(self):
        app = self.run_app()
        work = app.session_state["workspaces"]["new_account"]
        original = attachment("drivers_license")
        work["documents"] = [original, {**original, "id": "duplicate", "kind": "passport"}]
        self.field_by_key(app, f"field:{work['id']}:first_name").set_value("Staff entry").run()
        self.assertEqual(list(app.exception), [])
        self.assertEqual(work["documents"], [original])
        self.assertEqual(self.field_by_key(app, f"field:{work['id']}:first_name").value, "Staff entry")

    def test_comparison_panel_keeps_attachment_selector_image_and_download(self):
        app = self.run_app()
        work = app.session_state["workspaces"]["new_account"]
        work["documents"] = [attachment()]
        app.run()
        self.assertEqual(list(app.exception), [])
        selector = next(item for item in app.selectbox if item.label == "Preview attachment")
        self.assertEqual(selector.options, ["sample.png"])
        self.assertGreaterEqual(len(app.get("image")), 2)  # Documents and comparison previews.
        downloads = app.get("download_button")
        self.assertGreaterEqual(sum(item.label == "Download original" for item in downloads), 2)
        self.assertFalse(any("no attachments yet" in item.value for item in app.info))

    def test_continue_and_save_draft_with_all_fields_blank(self):
        with tempfile.TemporaryDirectory() as root, patch.object(store, "RECORDS_DIR", Path(root)):
            app = self.run_app()
            work = app.session_state["workspaces"]["new_account"]
            self.button_by_label(app, "Continue to Review fields").click().run()
            self.assertEqual(app.session_state["steps:" + work["id"]], "2 · Review fields")
            self.button_by_label(app, "Continue to Save & report").click().run()
            self.assertEqual(list(app.exception), [])
            self.assertEqual(app.session_state["steps:" + work["id"]], "3 · Save & report")
            self.assertFalse(self.button_by_label(app, "Save draft snapshot").disabled)
            self.assertTrue(self.button_by_label(app, "Save reviewed application").disabled)
            self.button_by_label(app, "Save draft snapshot").click().run()
            self.assertEqual(list(app.exception), [])
            records = store.list_applications(root)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["status"], "draft")
            record, docs = store.load_application(records[0]["id"], root)
            self.assertFalse(any(record["fields"].values()))
            self.assertEqual(docs, [])


if __name__ == "__main__":
    unittest.main()
