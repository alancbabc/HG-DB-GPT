import assert from 'node:assert/strict';
import test from 'node:test';

import { DEFAULT_UI_VISIBILITY, isRecommendedExampleVisible, resolveUiVisibilityConfig } from './ui-visibility';

test('fails open when the runtime config is missing or unsupported', () => {
  assert.deepEqual(resolveUiVisibilityConfig(undefined), DEFAULT_UI_VISIBILITY);
  assert.deepEqual(resolveUiVisibilityConfig({ version: 2 }), DEFAULT_UI_VISIBILITY);
});

test('applies valid visibility overrides without changing omitted defaults', () => {
  const config = resolveUiVisibilityConfig({
    version: 1,
    navigation: { skills: false, applications: false },
    explore: { skillSelector: false, recommendedExampleIds: ['db_profile_report'] },
  });

  assert.equal(config.navigation.skills, false);
  assert.equal(config.navigation.applications, false);
  assert.equal(config.navigation.dataSources, true);
  assert.equal(config.explore.skillSelector, false);
  assert.equal(config.explore.fileUpload, true);
  assert.equal(isRecommendedExampleVisible(config, 'db_profile_report'), true);
  assert.equal(isRecommendedExampleVisible(config, 'walmart_sales'), false);
});

test('ignores malformed leaves instead of accidentally hiding features', () => {
  const config = resolveUiVisibilityConfig({
    version: 1,
    navigation: { skills: 'false' },
    explore: { connectorSelector: 0, recommendedExampleIds: [42] },
  });

  assert.equal(config.navigation.skills, true);
  assert.equal(config.explore.connectorSelector, true);
  assert.equal(config.explore.recommendedExampleIds, 'all');
});
