# Contributing to InvoiceFlow Agent

First off, thank you for considering contributing to InvoiceFlow Agent! It's people like you that make this project great.

## Code of Conduct

This project and everyone participating in it is governed by our [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code.

## How Can I Contribute?

### Reporting Bugs

Before creating bug reports, please check the existing issues as you might find out that you don't need to create one. When you are creating a bug report, please include as many details as possible:

- **Use a clear and descriptive title**
- **Describe the exact steps which reproduce the problem**
- **Provide specific examples to demonstrate the steps**
- **Describe the behavior you observed after following the steps**
- **Explain which behavior you expected to see instead and why**
- **Include screenshots and animated GIFs if possible**

### Suggesting Enhancements

Enhancement suggestions are tracked as GitHub issues. When creating an enhancement suggestion, please include:

- **Use a clear and descriptive title**
- **Provide a step-by-step description of the suggested enhancement**
- **Provide specific examples to demonstrate the steps**
- **Describe the current behavior and explain which behavior you expected to see instead**
- **Explain why this enhancement would be useful**

### Pull Requests

1. **Fork the repository** and create your branch from `main`
2. **Follow the coding standards** outlined below
3. **Write tests** for your changes when applicable
4. **Ensure all tests pass** and the code builds successfully
5. **Update documentation** as needed
6. **Submit a pull request** with a clear title and description

## Development Workflow

### Setting Up Your Development Environment

1. **Clone the repository**
   ```bash
   git clone https://github.com/jadenfix/InvoiceFlowAgent.git
   cd InvoiceFlowAgent
   ```

2. **Install prerequisites**
   - AWS CLI configured with appropriate permissions
   - Terraform >= 1.5.0
   - Docker
   - kubectl
   - Helm

3. **Set up pre-commit hooks**
   ```bash
   pip install pre-commit
   pre-commit install
   ```

### Branch Naming Convention

Use descriptive branch names with the following prefixes:
- `feature/` - New features
- `fix/` - Bug fixes
- `docs/` - Documentation updates
- `refactor/` - Code refactoring
- `test/` - Test-related changes
- `chore/` - Maintenance tasks

Example: `feature/invoice-processing-api`

### Commit Message Guidelines

Follow the [Conventional Commits](https://www.conventionalcommits.org/) specification:

```
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

Types:
- `feat`: A new feature
- `fix`: A bug fix
- `docs`: Documentation only changes
- `style`: Changes that do not affect the meaning of the code
- `refactor`: A code change that neither fixes a bug nor adds a feature
- `test`: Adding missing tests or correcting existing tests
- `chore`: Changes to the build process or auxiliary tools

Examples:
```
feat(api): add invoice validation endpoint
fix(database): resolve connection timeout issue
docs(readme): update installation instructions
```

## Coding Standards

### Terraform

- Use consistent formatting with `terraform fmt`
- Follow Terraform naming conventions
- Include comments for complex logic
- Use variables for all configurable values
- Include proper outputs for all modules
- Follow the principle of least privilege for IAM policies

### Docker

- Use multi-stage builds when appropriate
- Minimize image size
- Use specific version tags, avoid `latest`
- Include health checks
- Use non-root users when possible

### Kubernetes

- Use resource limits and requests
- Include proper labels and annotations
- Use ConfigMaps and Secrets appropriately
- Follow security best practices

### General

- Write self-documenting code
- Include unit tests for new functionality
- Update integration tests as needed
- Ensure code is properly commented
- Follow language-specific style guides

## Testing

### Infrastructure Testing

- All Terraform code should be validated using `terraform validate`
- Run security scans using Checkov and TFSec
- Test infrastructure changes in dev environment first

### Application Testing

- Write unit tests for new functions and methods
- Include integration tests for API endpoints
- Ensure tests are idempotent and can run in parallel
- Aim for at least 80% code coverage

### Running Tests

```bash
# Terraform validation
terraform fmt -check -recursive infra/
terraform validate

# Security scans
checkov -d infra/
tfsec infra/

# Application tests (example for Node.js service)
cd services/invoice-processor
npm test
npm run test:integration
```

## Documentation

- Update README.md if your changes affect setup or usage
- Update API documentation for service changes
- Include inline code comments for complex logic
- Update architectural documentation for significant changes
- Ensure all new configuration options are documented

## Infrastructure Changes

### Terraform Best Practices

1. **Module Development**
   - Keep modules focused and reusable
   - Include comprehensive variable descriptions
   - Provide meaningful outputs
   - Include examples in module documentation

2. **State Management**
   - Never commit state files
   - Use remote state backends
   - Lock state during operations
   - Tag all resources appropriately

3. **Security**
   - Use least privilege access
   - Encrypt all data at rest and in transit
   - Regularly rotate secrets
   - Enable audit logging

### Adding New Environments

1. Create new environment directory under `infra/environments/`
2. Copy and modify variables from existing environment
3. Update CI/CD pipeline to include new environment
4. Test thoroughly in isolation

## Release Process

1. **Feature Development**
   - Create feature branch from `main`
   - Develop and test locally
   - Submit PR to `develop` branch

2. **Development Integration**
   - PRs are merged to `develop`
   - Automated deployment to dev environment
   - Integration testing in dev environment

3. **Staging Release**
   - Merge `develop` to `main`
   - Automated deployment to staging
   - User acceptance testing

4. **Production Release**
   - Manual approval required for production
   - Automated deployment with additional safeguards
   - Post-deployment monitoring

## Security Guidelines

- Never commit secrets or credentials
- Use AWS Secrets Manager or similar for sensitive data
- Follow the principle of least privilege
- Enable audit logging for all environments
- Regularly update dependencies
- Scan for vulnerabilities in CI/CD pipeline

## Getting Help

- Check existing [documentation](docs/)
- Search [existing issues](https://github.com/jadenfix/InvoiceFlowAgent/issues)
- Ask questions in [discussions](https://github.com/jadenfix/InvoiceFlowAgent/discussions)
- Contact maintainers via email for sensitive issues

## Recognition

Contributors will be recognized in our [Contributors](CONTRIBUTORS.md) file and in release notes.

Thank you for contributing to InvoiceFlow Agent! 🚀 