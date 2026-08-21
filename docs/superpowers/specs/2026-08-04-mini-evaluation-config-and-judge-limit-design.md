# Mini Evaluation Config and Judge Limit Design

## Goal

Allow `mini_demo` to run `deepseek-v4-flash`, `Kimi-K3`, and `GLM-5.2` from one local configuration file while raising the default Judge output limit to 8192 tokens.

## Configuration

`mini_demo/config.env` is the local runtime configuration. It is ignored by Git and may contain real credentials. `mini_demo/config.env.example` is committed with placeholders only.

The default inference variables serve models that share the SCNet endpoint:

- `INFER_API_KEY`
- `INFER_BASE_URL`

`deepseek-v4-flash` uses model-specific overrides:

- `DEEPSEEK_V4_FLASH_INFER_API_KEY`
- `DEEPSEEK_V4_FLASH_INFER_BASE_URL`

All LLM Judge calls use:

- `JUDGE_API_KEY`
- `JUDGE_BASE_URL`
- `JUDGE_MODEL`

## Loading and Resolution

`mini_demo/run.sh` automatically loads `mini_demo/config.env` before validating required variables. Existing exported environment variables take precedence so temporary overrides remain possible.

`mini_eval.py` resolves inference credentials per model. For `deepseek-v4-flash`, it uses the model-specific variables when both are set; otherwise it falls back to the default `INFER_*` variables. Other models use the default variables.

## Judge Limit

The default value of `--judge-max-tokens` changes from 512 to 8192. An explicit CLI value still takes precedence.

This change only raises the Judge output limit. It does not add structured verdict or reason fields and does not change score parsing.

## Security

`config.env` must have mode `600`. Tests and output files must not contain API keys. The example configuration contains no real credentials.

## Verification

- Unit tests cover the new 8192 default and per-model inference resolution.
- Shell validation covers automatic configuration loading without exposing values.
- Existing `mini_demo` tests continue to pass.
- An online smoke test runs three models across four datasets with `--limit 1`, for 12 inference samples total.
