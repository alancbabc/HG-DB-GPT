import assert from 'node:assert/strict';
import test from 'node:test';

import {
  DEFAULT_UI_VISIBILITY,
  isRecommendedExampleVisible,
  resolveUiVisibilityConfig,
  UI_VISIBILITY_CACHE_KEY,
} from './ui-visibility';

test('uses a versioned cache key for the last known runtime configuration', () => {
  assert.equal(UI_VISIBILITY_CACHE_KEY, 'dbgpt.ui-visibility.v1');
});

test('fails open when the runtime config is missing or unsupported', () => {
  assert.deepEqual(resolveUiVisibilityConfig(undefined), DEFAULT_UI_VISIBILITY);
  assert.deepEqual(resolveUiVisibilityConfig({ version: 2 }), DEFAULT_UI_VISIBILITY);
});

test('applies valid visibility overrides without changing omitted defaults', () => {
  const config = resolveUiVisibilityConfig({
    version: 1,
    navigation: { skills: false, applications: false },
    explore: { skillSelector: false, recommendedExampleIds: ['db_profile_report'] },
    sidebar: { newTask: false },
  });

  assert.equal(config.navigation.skills, false);
  assert.equal(config.navigation.applications, false);
  assert.equal(config.navigation.dataSources, true);
  assert.equal(config.explore.skillSelector, false);
  assert.equal(config.explore.fileUpload, true);
  assert.equal(config.sidebar.userProfile, true);
  assert.equal(config.sidebar.newTask, false);
  assert.equal(isRecommendedExampleVisible(config, 'db_profile_report'), true);
  assert.equal(isRecommendedExampleVisible(config, 'walmart_sales'), false);
});

test('ignores malformed leaves instead of accidentally hiding features', () => {
  const config = resolveUiVisibilityConfig({
    version: 1,
    navigation: { skills: 'false' },
    explore: { connectorSelector: 0, recommendedExampleIds: [42] },
    sidebar: { userProfile: 'false', newTask: 'false' },
  });

  assert.equal(config.navigation.skills, true);
  assert.equal(config.explore.connectorSelector, true);
  assert.equal(config.sidebar.userProfile, true);
  assert.equal(config.sidebar.newTask, true);
  assert.equal(config.explore.recommendedExampleIds, 'all');
});
