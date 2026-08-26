package com.netgrif.etask.startup

import com.netgrif.application.engine.startup.*

class EtaskRunnerController extends RunnerController {

    private List order = [
            ElasticsearchRunner,
            MongoDbRunner,
            StorageRunner,
            RuleEngineRunner,
            DefaultRoleRunner,
            AnonymousRoleRunner,
            AuthorityRunner,
            SystemUserRunner,
            UriRunner,
            FunctionsCacheRunner,
            FilterRunner,
            GroupRunner,
            DefaultFiltersRunner,
            ImpersonationRunner,
            DashboardRunner,
            SuperCreator,
            FlushSessionsRunner,
            MailRunner,
            PostalCodeImporter,
            // CUSTOM IMPORT RUNNERS
            NetRunner,
            // END OF CUSTOM IMPORT RUNNERS
            DemoRunner,
            QuartzSchedulerRunner,
            PdfRunner,
            // ADDITIONAL CUSTOM RUNNERS
            EtaskRunner,
            EtaskUserCreator,
            // Must run after NetRunner: uri nodes only exist once the processes
            // whose identifiers carry their path have been imported.
            UriNodeDataRunner,
            // Must run after NetRunner too: it creates one case per process
            // listed in `bootstrapCase`, and those processes build the menu views.
            BootstrapCaseRunner,
            // END OF ADDITIONAL CUSTOM RUNNERS
            FinisherRunnerSuperCreator,
            FinisherRunner,
    ]

    @Override
    protected List getOrderList() {
        return order
    }

}
