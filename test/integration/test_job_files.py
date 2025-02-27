"""Warning - this is hard to test.

This is a terrible API to test - the state of what is allowed is
highly dependent on the state of the job - which Galaxy typically
tries to get running and finish ASAP. Additionally, what is allowed
is very dependent on Galaxy internals about how the job working
directory is structured.

An ideal test would be to run Pulsar and Galaxy on different disk
and different servers and have them talk to each other - but this
still wouldn't test security stuff.

As a result this test is highly coupled with internals in a way most
integration tests avoid - but @jmchilton's fear of not touching this
API has gone too far.
"""
import io
import os
import tempfile

import requests
from sqlalchemy import select

from galaxy import model
from galaxy.model.base import transaction
from galaxy_test.base import api_asserts
from galaxy_test.base.populators import DatasetPopulator
from galaxy_test.driver import integration_util

SCRIPT_DIRECTORY = os.path.abspath(os.path.dirname(__file__))
SIMPLE_JOB_CONFIG_FILE = os.path.join(SCRIPT_DIRECTORY, "simple_job_conf.xml")

TEST_INPUT_TEXT = "test input content\n"
TEST_FILE_IO = io.StringIO("some initial text data")


class TestJobFilesIntegration(integration_util.IntegrationTestCase):
    initialized = False

    @classmethod
    def handle_galaxy_config_kwds(cls, config):
        super().handle_galaxy_config_kwds(config)
        config["job_config_file"] = SIMPLE_JOB_CONFIG_FILE
        config["object_store_store_by"] = "uuid"
        config["server_name"] = "files"
        cls.initialized = False

    def setUp(self):
        super().setUp()
        self.dataset_populator = DatasetPopulator(self.galaxy_interactor)
        if not TestJobFilesIntegration.initialized:
            history_id = self.dataset_populator.new_history()
            sa_session = self.sa_session
            stmt = select(model.HistoryDatasetAssociation)
            assert len(sa_session.scalars(stmt).all()) == 0
            self.dataset_populator.new_dataset(history_id, content=TEST_INPUT_TEXT, wait=True)
            assert len(sa_session.scalars(stmt).all()) == 1
            self.input_hda = sa_session.scalars(stmt).all()[0]
            TestJobFilesIntegration.initialized = True

    def test_read_by_state(self):
        job, _, _ = self.create_static_job_with_state("running")
        job_id, job_key = self._api_job_keys(job)
        data = {"path": self.input_hda.file_name, "job_key": job_key}
        get_url = self._api_url(f"jobs/{job_id}/files", use_key=True)
        response = requests.get(get_url, params=data)
        api_asserts.assert_status_code_is_ok(response)
        assert response.text == TEST_INPUT_TEXT

        # set job state to finished and ensure the file is no longer
        # readable
        self._change_job_state(job, "ok")

        get_url = self._api_url(f"jobs/{job_id}/files", use_key=True)
        response = requests.get(get_url, params=data)
        _assert_insufficient_permissions(response)

    def test_write_by_state(self):
        job, output_hda, working_directory = self.create_static_job_with_state("running")
        job_id, job_key = self._api_job_keys(job)
        path = self._app.object_store.get_filename(output_hda.dataset)
        assert path
        data = {"path": path, "job_key": job_key}

        def files():
            return {"file": io.StringIO("some initial text data")}

        post_url = self._api_url(f"jobs/{job_id}/files", use_key=False)
        response = requests.post(post_url, data=data, files=files())
        api_asserts.assert_status_code_is_ok(response)
        assert open(path).read() == "some initial text data"

        work_dir_file = os.path.join(working_directory, "work")
        data = {"path": work_dir_file, "job_key": job_key}
        response = requests.post(post_url, data=data, files=files())
        api_asserts.assert_status_code_is_ok(response)
        assert open(work_dir_file).read() == "some initial text data"

        # set job state to finished and ensure the file is no longer
        # readable
        self._change_job_state(job, "ok")

        response = requests.post(post_url, data=data, files=files())
        _assert_insufficient_permissions(response)

    def test_write_protection(self):
        job, _, _ = self.create_static_job_with_state("running")
        job_id, job_key = self._api_job_keys(job)
        t_file = tempfile.NamedTemporaryFile()
        data = {"path": t_file.name, "job_key": job_key}
        file = io.StringIO("some initial text data")
        files = {"file": file}
        post_url = self._api_url(f"jobs/{job_id}/files", use_key=True)
        response = requests.post(post_url, data=data, files=files)
        _assert_insufficient_permissions(response)

    @property
    def sa_session(self):
        return self._app.model.session

    def create_static_job_with_state(self, state):
        """Create a job with unknown handler so its state won't change."""
        sa_session = self.sa_session
        hda = sa_session.scalars(select(model.HistoryDatasetAssociation)).all()[0]
        assert hda
        history = sa_session.scalars(select(model.History)).all()[0]
        assert history
        user = sa_session.scalars(select(model.User)).all()[0]
        assert user
        output_hda = model.HistoryDatasetAssociation(history=history, create_dataset=True, flush=False)
        output_hda.hid = 2
        sa_session.add(output_hda)
        with transaction(sa_session):
            sa_session.commit()
        job = model.Job()
        job.history = history
        job.user = user
        job.handler = "unknown-handler"
        job.state = state
        sa_session.add(job)
        job.add_input_dataset("input1", hda)
        job.add_output_dataset("output1", output_hda)
        with transaction(sa_session):
            sa_session.commit()
        self._app.object_store.create(output_hda.dataset)
        self._app.object_store.create(job, base_dir="job_work", dir_only=True, obj_dir=True)
        working_directory = self._app.object_store.get_filename(job, base_dir="job_work", dir_only=True, obj_dir=True)
        return job, output_hda, working_directory

    def _api_job_keys(self, job):
        job_id = self._app.security.encode_id(job.id)
        job_key = self._app.security.encode_id(job.id, kind="jobs_files")
        assert job_key
        return job_id, job_key

    def _change_job_state(self, job, state):
        job.state = state
        sa_session = self.sa_session
        sa_session.add(job)
        with transaction(sa_session):
            sa_session.commit()


def _assert_insufficient_permissions(response):
    api_asserts.assert_status_code_is(response, 403)
    api_asserts.assert_error_code_is(response, 403002)
