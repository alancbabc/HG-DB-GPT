# UI Visibility Configuration

`public/ui-visibility.json` is the only deployment-level source for desktop UI visibility. The typed resolver in `ui-visibility.ts` applies visible defaults to missing or invalid values.

| Key | Default | Scope | Runtime dependency retained |
| --- | --- | --- | --- |
| `navigation.explore` | `true` | Main sidebar | ReAct Agent |
| `navigation.skills` | `true` | Sidebar and management tabs | Skill APIs and `load_skill` |
| `navigation.dataSources` | `true` | Sidebar and management tabs | Database APIs and SQL tools |
| `navigation.knowledgeBases` | `true` | Sidebar and management tabs | Knowledge APIs and DAG runtime |
| `navigation.applications` | `true` | Management menu and tabs | Application APIs and registrations |
| `navigation.models` | `true` | Management menu and tabs | Model APIs and workers |
| `navigation.awelWorkflows` | `true` | Management menu and tabs | AWEL/DAG runtime and APIs |
| `navigation.prompts` | `true` | Management menu | Prompt APIs and stored prompts |
| `navigation.connectors` | `true` | Management menu and tabs | Connector manager, APIs and saved task payloads |
| `navigation.scheduledTasks` | `true` | Management menu and tabs | Scheduler and saved payloads |
| `navigation.dbgptsCommunity` | `true` | Management menu | DBGPTS APIs |
| `navigation.modelEvaluation` | `true` | Management menu | Evaluation APIs and routes |
| `explore.fileUpload` | `true` | Desktop composer | Session-file APIs and history |
| `explore.dataSourceSelector` | `true` | Desktop composer | Database context |
| `explore.knowledgeBaseSelector` | `true` | Desktop composer | Knowledge context |
| `explore.modelSelector` | `true` | Desktop composer | Model selection |
| `explore.skillSelector` | `true` | Desktop composer | Skill execution stays active |
| `explore.connectorSelector` | `true` | Desktop composer | Connector execution stays active |
| `explore.recommendedExampleIds` | `"all"` | Desktop example cards | Example APIs and assets |
| `sidebar.userProfile` | `true` | Desktop sidebar bottom profile | Authentication and user state remain unchanged |
| `sidebar.newTask` | `true` | Desktop sidebar new-task button | Conversation creation and routes remain unchanged |

Hidden routes remain directly accessible. Mobile chat is outside this configuration and remains unchanged.

`web/public/ui-visibility.json` is the editable source. Run `npm run sync:ui-visibility` from `web/` after changing it; use `npm run sync:ui-visibility -- --check` in CI to detect drift in the Python static bundle. The last successfully loaded configuration is cached per browser tab, so a transient config request failure does not restore the previous visible UI during refreshes.
