## Coding Style
- After modification to the code, run the `ruff` formatter to ensure consistent code style. 
- Use **f-strings** for string interpolations. Prefer `str.format()` for complex formatting to honor line character limit.
- When accessing dictionary keys, use direct access (e.g., `dict[key]`) instead of `dict.get()` when the type is known.
- When logging, include the relevant variables in the log message. For example:
  ```python
  logger.info(f"Set market order succeeded | pair={pair} amount={amount} price={price}")
  ```
- When raising exceptions, include relevant context in the exception message and add single quotes around variable names. For example:
  ```python
  raise ExchangeError(f"Failed to fetch ticker for '{pair}' on '{exchange_name}'")
  ```
- Break long strings into multiple lines to honor the line character limit. For example:
  ```python
  logger.info(
      f"Set market order succeeded | "
      f"pair={pair} amount={amount} price={price}"
  )
  ```
- Follow the Google Python Style Guide for docstring conventions. Use third-person descriptive style. Wrap code fragments in single backticks; when referencing symbols from the internal codebase, wrap them in double backticks. For example:
  ```python
  def fetch_data(self, base_url: str | None = None) -> dict:
      """Fetches data from the API and returns it as a dictionary.

      Args:
          `base_url`:
              The base URL for the API.
              If `None`, uses the default URL from ``self.base_url``.

      Raises:
          ``CustomConnectionError``:
              If there is a network issue while fetching data.
      """
      pass
  ```
- For descriptive comments, use third-person present participle style. For inline comments, use imperative style. For example:
  ```python
  # Fetching data from the API
  data = api.get_data()

  if data is None:
      return  # ignore network errors
  ```
- When defining classes, include a class-level docstring that describes the purpose and functionality of the class. For class properties docstrings, use third-person descriptive style. For example:
  ```python
  class ExchangeClient:
      """Client for interacting with the cryptocurrency exchange."""

      @property
      def name(self) -> Exchange:
          """The name of the exchange."""
          raise NotImplementedError()
  ```
- Always provide explicit type hints for function parameters and return value. Also for variables with empty initializers. For example:
  ```python
  def calculate_fee(self, amount: float, rate: float) -> float:
      """Calculates the transaction fee based on amount and rate."""
      fee: float | None = None
      if amount > 1000:
          fee = amount * rate * 0.9  # apply discount for large amounts
      else:
          fee = amount * rate

      return fee
  ```
- Avoid introducing variables that are used only once; inline the expression. For example:
  ```python
  # Original code
  result = compute_value()
  return result

  # Revised code
  return compute_value()
  ```
- In classes, the private methods should be defined before the public methods. The properties should be defined at the end of the class definition. For example:
  ```python
  class ExampleClass:
      def _private_method(self) -> None:
          pass

      def public_method(self) -> None:
          pass

      @property
      def example_property(self) -> str:
          pass
  ```

## Coding Practices
- Leverage latest language features of Python version that specified in `pyproject.toml` where appropriate.
- Always try to use only the features that are exist in Python's standard library unless there is no way to install external packages.
- When working with unknown data structures (e.g. API responses), do not try to guess the structure. Instead, use runtime inspection techniques such as printing the data or using debugging tools to understand the structure before proceeding.
