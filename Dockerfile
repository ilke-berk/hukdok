# Stage 1: Build the application
FROM node:20 AS builder

WORKDIR /app

# Copy package.json and ensure it exists
COPY package.json ./

# Install dependencies
# Using --legacy-peer-deps to ignore conflict between cleanup React 18 and MSAL v5 (which usually wants React 19)
RUN npm install --legacy-peer-deps

# Copy the rest of the application code
COPY . .

# Build the application
RUN npm run build

# Stage 2: Serve the application with Nginx
FROM nginx:alpine

# Copy the build output from the builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy custom Nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expose port 80
EXPOSE 80

# Start Nginx
CMD ["nginx", "-g", "daemon off;"]
