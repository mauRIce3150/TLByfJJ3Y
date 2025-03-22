# Financial Dashboard Architecture

This document provides a comprehensive overview of the Financial Dashboard application architecture and features.

## Project Overview

The Financial Dashboard is a serverless application built on AWS that allows users to track their financial transactions and monitor stock market data. The application showcases modern cloud architecture principles, serverless design patterns, and frontend development techniques.

## Key Features

- **Real-time Financial Data**: View up-to-date stock market data
- **Market Analysis**: Analyze stock performance and trends
- **User Authentication**: Secure user authentication and authorization
- **Responsive Design**: Optimized for desktop and mobile devices
- **Serverless Architecture**: Scalable and cost-effective infrastructure

## Technology Stack

### Frontend
- React.js
- Styled Components
- React Router
- Axios

### Backend
- AWS Lambda
- Amazon API Gateway
- Amazon DynamoDB
- Amazon Cognito

### Infrastructure
- Terraform
- AWS S3
- AWS CloudFront
- AWS DynamoDB

## Architecture Diagram

The architecture diagram is available as a Draw.io file at [images/architecture.drawio](images/architecture.drawio) and as a static image at [images/architecture.jpg](images/architecture.jpg).

![Financial Dashboard Architecture](images/architecture.jpg)

## Component Description

### Frontend Components

- **CloudFront**: Content delivery network for distributing the frontend application
  - Provides global distribution with low latency
  - Handles SSL/TLS termination
  - Caches static content for improved performance

- **S3 (Frontend)**: Hosts the static React.js frontend application
  - Stores HTML, CSS, JavaScript, and other static assets
  - Configured for web hosting
  - Private access, only accessible through CloudFront

- **Cognito**: Manages user authentication and authorization
  - Handles user registration and sign-in
  - Issues JWT tokens for API authorization
  - Supports social identity providers (Google, Facebook, etc.)

### Backend Components

- **API Gateway**: Provides RESTful API endpoints for the frontend with the following routes:
  - `/auth` (POST): Authentication endpoint
  - `/transactions` (GET, POST): Transaction management
  - `/user/profile` (GET, POST): User profile management
  - `/market/data` (GET): Market data retrieval

- **Lambda Functions**:
  - **Auth Lambda**: Handles user authentication and authorization with Cognito
    - Validates user credentials
    - Issues and validates JWT tokens
    - Manages user sessions

  - **Market Lambda**: Retrieves stock market data from Alpha Vantage API
    - Fetches real-time stock quotes
    - Retrieves historical stock data
    - Implements caching to reduce API calls

  - **User Lambda**: Manages user profiles and preferences stored in DynamoDB
    - Creates and updates user profiles
    - Manages user preferences and settings
    - Handles user-specific configurations

  - **Transactions Lambda**: Handles financial transaction operations
    - Creates new financial transactions
    - Retrieves transaction history
    - Generates transaction reports and summaries

- **DynamoDB Tables**:
  - **User Settings Table**: Stores user preferences and settings
    - Primary key: userId (String)
    - Stores theme preferences, dashboard configurations, etc.
    - Supports on-demand capacity mode for automatic scaling

  - **Transactions Table**: Stores financial transaction data
    - Hash key: userId (String)
    - Range key: id (String)
    - Global Secondary Index: DateIndex (userId + date)
    - Stores transaction amount, category, date, description, etc.

- **External API**:
  - **Alpha Vantage API**: Third-party API for retrieving real-time stock market data
    - Provides stock quotes, historical data, and technical indicators
    - Free tier with limited API calls per day
    - Fallback mechanisms implemented for API rate limiting

## Data Flow

1. **User Authentication**:
   - User logs in through the frontend application
   - Authentication request is sent to API Gateway's `/auth` endpoint
   - Auth Lambda validates credentials with Cognito
   - Cognito returns JWT tokens for subsequent API calls

2. **Market Data Retrieval**:
   - Frontend requests stock data from API Gateway's `/market/data` endpoint
   - API Gateway routes request to Market Lambda
   - Market Lambda retrieves data from Alpha Vantage API
   - Data is returned to the frontend for display

3. **User Profile Management**:
   - Frontend sends user profile operations to API Gateway's `/user/profile` endpoint
   - API Gateway routes request to User Lambda
   - User Lambda performs operations on the User Settings DynamoDB table
   - Results are returned to the frontend

4. **Transaction Management**:
   - Frontend sends transaction operations to API Gateway's `/transactions` endpoint
   - API Gateway routes request to Transactions Lambda
   - Transactions Lambda performs CRUD operations on the Transactions DynamoDB table
   - Results are returned to the frontend

## Security Considerations

- **Authentication**: Cognito handles user authentication and provides JWT tokens
- **Authorization**: API Gateway validates JWT tokens for each request using a Cognito authorizer
- **Data Encryption**: All data is encrypted in transit using HTTPS
- **Access Control**: IAM roles and policies restrict Lambda access to specific DynamoDB tables
- **Least Privilege**: Each Lambda function has only the permissions it needs to perform its tasks
- **API Rate Limiting**: API Gateway implements throttling to prevent abuse

## Scalability

The serverless architecture allows the application to scale automatically based on demand:

- **Lambda Functions**: Scale automatically based on the number of incoming requests
- **DynamoDB**: Uses on-demand capacity mode to scale read and write operations based on traffic
- **CloudFront**: Distributes content globally with edge caching
- **API Gateway**: Handles thousands of concurrent API calls

## Monitoring and Logging

- **CloudWatch Logs**: All Lambda functions log to CloudWatch for centralized logging
- **CloudWatch Metrics**: Monitors API Gateway, Lambda, and DynamoDB performance
- **X-Ray Tracing**: Distributed tracing for request flows across services
- **Alarms**: Configured for critical metrics to alert on issues

## Cost Optimization

- **Serverless Architecture**: Pay only for what you use
- **CloudFront Caching**: Reduces origin requests to S3
- **Lambda Optimization**: Functions sized appropriately for their workload
- **DynamoDB On-Demand**: Scales automatically without over-provisioning

## Project Purpose

This project was created to demonstrate proficiency in:

1. Serverless architecture design
2. AWS cloud services implementation
3. Infrastructure as Code using Terraform
4. Modern frontend development with React
5. Secure authentication and authorization
6. API design and implementation

The application showcases best practices in cloud architecture, including scalability, security, and cost optimization. 