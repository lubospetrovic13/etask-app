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
            // Must run after NetRunner: it creates one case per process listed
            // in `bootstrapCase`, and those processes build the menu views.
            BootstrapCaseRunner,
            // Must run after BOTH of those. After NetRunner, because most uri
            // nodes only exist once the process whose identifier carries their
            // path is imported. And after BootstrapCaseRunner, because a node
            // that NO identifier carries - `general`, the admin catalogue - is
            // created by a menu-building action, and those run from bootstrap
            // cases.
            //
            // When this ran before BootstrapCaseRunner, `general` did not exist
            // yet, so this runner skipped it ("does not exist yet") and the node
            // ended up with no UriNodeData at all. A node without data is
            // visible to EVERYONE (fail-open, by design), so on a fresh database
            // the admin-only catalogue was visible to every logged-in user -
            // silently, and only on a fresh database.
            UriNodeDataRunner,
            // END OF ADDITIONAL CUSTOM RUNNERS
            FinisherRunnerSuperCreator,
            FinisherRunner,
    ]

    @Override
    protected List getOrderList() {
        return order
    }

}
