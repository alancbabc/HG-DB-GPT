export const UI_VISIBILITY_CONFIG_URL = '/ui-visibility.json';
export const UI_VISIBILITY_CACHE_KEY = 'dbgpt.ui-visibility.v1';
export const UI_VISIBILITY_CONFIG_VERSION = 1 as const;

export interface NavigationVisibility {
  explore: boolean;
  skills: boolean;
  dataSources: boolean;
  knowledgeBases: boolean;
  applications: boolean;
  models: boolean;
  awelWorkflows: boolean;
  prompts: boolean;
  connectors: boolean;
  scheduledTasks: boolean;
  dbgptsCommunity: boolean;
  modelEvaluation: boolean;
}

export interface ExploreVisibility {
  fileUpload: boolean;
  dataSourceSelector: boolean;
  knowledgeBaseSelector: boolean;
  modelSelector: boolean;
  skillSelector: boolean;
  connectorSelector: boolean;
  recommendedExampleIds: 'all' | string[];
}

export interface SidebarVisibility {
  userProfile: boolean;
  newTask: boolean;
}

export interface UiVisibilityConfig {
  version: typeof UI_VISIBILITY_CONFIG_VERSION;
  navigation: NavigationVisibility;
  explore: ExploreVisibility;
  sidebar: SidebarVisibility;
}

export const DEFAULT_UI_VISIBILITY: UiVisibilityConfig = {
  version: UI_VISIBILITY_CONFIG_VERSION,
  navigation: {
    explore: true,
    skills: true,
    dataSources: true,
    knowledgeBases: true,
    applications: true,
    models: true,
    awelWorkflows: true,
    prompts: true,
    connectors: true,
    scheduledTasks: true,
    dbgptsCommunity: true,
    modelEvaluation: true,
  },
  explore: {
    fileUpload: true,
    dataSourceSelector: true,
    knowledgeBaseSelector: true,
    modelSelector: true,
    skillSelector: true,
    connectorSelector: true,
    recommendedExampleIds: 'all',
  },
  sidebar: {
    userProfile: true,
    newTask: true,
  },
};

const NAVIGATION_KEYS: Array<keyof NavigationVisibility> = [
  'explore',
  'skills',
  'dataSources',
  'knowledgeBases',
  'applications',
  'models',
  'awelWorkflows',
  'prompts',
  'connectors',
  'scheduledTasks',
  'dbgptsCommunity',
  'modelEvaluation',
];

const EXPLORE_BOOLEAN_KEYS: Array<Exclude<keyof ExploreVisibility, 'recommendedExampleIds'>> = [
  'fileUpload',
  'dataSourceSelector',
  'knowledgeBaseSelector',
  'modelSelector',
  'skillSelector',
  'connectorSelector',
];

const SIDEBAR_BOOLEAN_KEYS: Array<keyof SidebarVisibility> = ['userProfile', 'newTask'];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function cloneDefaults(): UiVisibilityConfig {
  return {
    version: UI_VISIBILITY_CONFIG_VERSION,
    navigation: { ...DEFAULT_UI_VISIBILITY.navigation },
    explore: { ...DEFAULT_UI_VISIBILITY.explore },
    sidebar: { ...DEFAULT_UI_VISIBILITY.sidebar },
  };
}

/** Merge only valid leaves. Missing or malformed values remain visible. */
export function resolveUiVisibilityConfig(value: unknown): UiVisibilityConfig {
  const resolved = cloneDefaults();
  if (!isRecord(value) || value.version !== UI_VISIBILITY_CONFIG_VERSION) return resolved;

  if (isRecord(value.navigation)) {
    for (const key of NAVIGATION_KEYS) {
      const candidate = value.navigation[key];
      if (typeof candidate === 'boolean') resolved.navigation[key] = candidate;
    }
  }

  if (isRecord(value.explore)) {
    for (const key of EXPLORE_BOOLEAN_KEYS) {
      const candidate = value.explore[key];
      if (typeof candidate === 'boolean') resolved.explore[key] = candidate;
    }

    const exampleIds = value.explore.recommendedExampleIds;
    if (exampleIds === 'all' || (Array.isArray(exampleIds) && exampleIds.every(id => typeof id === 'string'))) {
      resolved.explore.recommendedExampleIds = exampleIds === 'all' ? 'all' : [...exampleIds];
    }
  }

  if (isRecord(value.sidebar)) {
    for (const key of SIDEBAR_BOOLEAN_KEYS) {
      const candidate = value.sidebar[key];
      if (typeof candidate === 'boolean') resolved.sidebar[key] = candidate;
    }
  }

  return resolved;
}

export function isRecommendedExampleVisible(config: UiVisibilityConfig, exampleId: string): boolean {
  const allowedIds = config.explore.recommendedExampleIds;
  return allowedIds === 'all' || allowedIds.includes(exampleId);
}
