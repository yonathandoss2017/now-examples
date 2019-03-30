# Charge.js Example

This directory is a brief example of a [Charge.js](https://charge.js.org/) site using the [@now/static-build](https://zeit.co/docs/v2/deployments/official-builders/static-build-now-static-build) builder.

The example consists of one source directory, `/source`, which contains an index and layout component. `/source` also includes a `/pages` directory where `.mdx` files are stored. This file structure is very basic as Charge focuses on simplicity, however, you are free to use whatever file structure suits your needs best.

The example also includes a `now.json` file, this is used to configure your build when deploying to Now. The `package.json` has seen some minor changes with the addition of scrips from the Charge.js [documentation](https://charge.js.org/usage) along with a `now-build` script used by Now in deployment.

## Resources

For more information on how you can deploy your own Charge.js sites, see the following resources:

- [Our Static Builder (@now/static-build) documentation](https://zeit.co/docs/v2/deployments/official-builders/static-build-now-static-build)
- [The basics of deploying on Now](https://zeit.co/docs/v2/deployments/basics/)
- [The official Charge.js documentation](https://charge.js.org/)
