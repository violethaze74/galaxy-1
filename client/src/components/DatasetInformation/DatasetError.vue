<template>
    <div>
        <b-alert v-if="errorMessage" variant="danger" show>
            <h2 class="alert-heading h-sm">Failed to access Dataset details.</h2>
            {{ errorMessage }}
        </b-alert>
        <DatasetProvider :id="datasetId" v-slot="{ result: dataset, loading: datasetLoading }">
            <JobDetailsProvider
                v-if="!datasetLoading"
                v-slot="{ result: jobDetails, loading }"
                :job-id="dataset.creating_job"
                @error="onError">
                <div v-if="!loading">
                    <div class="page-container edit-attr">
                        <div class="response-message"></div>
                    </div>
                    <h3 class="h-lg">Dataset Error Report</h3>
                    <p>
                        An error occurred while running the tool
                        <b id="dataset-error-tool-id" class="text-break">{{ jobDetails.tool_id }}</b
                        >.
                    </p>
                    <DatasetErrorDetails
                        :tool-stderr="jobDetails.tool_stderr"
                        :job-stderr="jobDetails.job_stderr"
                        :job-messages="jobDetails.job_messages" />
                    <JobProblemProvider
                        v-slot="{ result: jobProblems }"
                        :job-id="dataset.creating_job"
                        @error="onError">
                        <div v-if="jobProblems && (jobProblems.has_duplicate_inputs || jobProblems.has_empty_inputs)">
                            <h4 class="common_problems mt-3 h-md">Detected Common Potential Problems</h4>
                            <p v-if="jobProblems.has_empty_inputs" id="dataset-error-has-empty-inputs">
                                The tool was started with one or more empty input datasets. This frequently results in
                                tool errors due to problematic input choices.
                            </p>
                            <p v-if="jobProblems.has_duplicate_inputs" id="dataset-error-has-duplicate-inputs">
                                The tool was started with one or more duplicate input datasets. This frequently results
                                in tool errors due to problematic input choices.
                            </p>
                        </div>
                    </JobProblemProvider>
                    <h4 class="mt-3 h-md">Troubleshooting</h4>
                    <p>
                        There are a number of helpful resources to self diagnose and correct problems.
                        <br />
                        Start here:
                        <b>
                            <a
                                href="https://training.galaxyproject.org/training-material/faqs/galaxy/#troubleshooting-errors"
                                target="_blank">
                                My job ended with an error. What can I do?
                            </a>
                        </b>
                    </p>
                    <h4 class="mb-3 h-md">Issue Report</h4>
                    <b-alert
                        v-for="(resultMessage, index) in resultMessages"
                        :key="index"
                        :variant="resultMessage[1]"
                        show>
                        <span v-html="renderMarkdown(resultMessage[0])"></span>
                    </b-alert>
                    <div v-if="showForm" id="fieldsAndButton">
                        <span class="mr-2 font-weight-bold">{{ emailTitle }}</span>
                        <span v-if="!!currentUser?.email">{{ currentUser?.email }}</span>
                        <span v-else>{{ "You must be logged in to receive emails" | l }}</span>
                        <FormElement
                            id="dataset-error-message"
                            v-model="message"
                            :area="true"
                            title="Please provide detailed information on the activities leading to this issue:" />
                        <b-button
                            id="dataset-error-submit"
                            variant="primary"
                            class="mt-3"
                            @click="submit(dataset, jobDetails.user_email)">
                            <FontAwesomeIcon icon="bug" class="mr-1" />Report
                        </b-button>
                    </div>
                </div>
            </JobDetailsProvider>
        </DatasetProvider>
    </div>
</template>

<script>
import { library } from "@fortawesome/fontawesome-svg-core";
import { faBug } from "@fortawesome/free-solid-svg-icons";
import { FontAwesomeIcon } from "@fortawesome/vue-fontawesome";
import FormElement from "components/Form/FormElement";
import { DatasetProvider } from "components/providers";
import { JobDetailsProvider, JobProblemProvider } from "components/providers/JobProvider";
import { mapState } from "pinia";

import { useMarkdown } from "@/composables/markdown";
import { useUserStore } from "@/stores/userStore";

import DatasetErrorDetails from "./DatasetErrorDetails";
import { sendErrorReport } from "./services";

library.add(faBug);

export default {
    components: {
        DatasetProvider,
        DatasetErrorDetails,
        FontAwesomeIcon,
        FormElement,
        JobDetailsProvider,
        JobProblemProvider,
    },
    props: {
        datasetId: {
            type: String,
            required: true,
        },
    },
    setup() {
        const { renderMarkdown } = useMarkdown({ openLinksInNewPage: true });
        return { renderMarkdown };
    },
    data() {
        return {
            message: null,
            errorMessage: null,
            resultMessages: [],
            emailTitle: this.l("Your email address"),
        };
    },
    computed: {
        ...mapState(useUserStore, ["currentUser"]),
        showForm() {
            const noResult = !this.resultMessages.length;
            const hasError = this.resultMessages.some((msg) => msg[1] === "danger");
            return noResult || hasError;
        },
    },
    methods: {
        onError(err) {
            this.errorMessage = err;
        },
        submit(dataset, userEmailJob) {
            const email = userEmailJob || this.currentUserEmail;
            const message = this.message;
            sendErrorReport(dataset, message, email).then(
                (resultMessages) => {
                    this.resultMessages = resultMessages;
                },
                (errorMessage) => {
                    this.errorMessage = errorMessage;
                }
            );
        },
    },
};
</script>
