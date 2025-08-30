# 🔹 How EC2, Jenkins, Docker, and `usermod` Work Together

## 1. **EC2 = The Host Machine**
* Think of your **AWS EC2** as a **physical server in the cloud**.
* It provides the OS (Ubuntu in your case).
* On this EC2, you installed:
   * **Jenkins** (automation server).
   * **Docker** (container runtime).

So, **EC2 is the foundation** — Jenkins and Docker both run on it.

## 2. **Jenkins on EC2**
* Jenkins is installed as a **service** on EC2 (usually runs on port 8080).
* It executes jobs (pipelines) on the EC2 host.
* Whenever Jenkins runs a `sh` step in a pipeline, it's really **just running a Linux shell command on your EC2 instance**.

Example:
```bash
sh 'docker build -t htmlapp:latest .'
```

This command is executed **by Jenkins on the EC2 machine**, which means Jenkins needs permission to talk to Docker.

## 3. **Docker on EC2**
* Docker daemon (`dockerd`) runs in the background on EC2.
* It listens on a **Unix socket** (`/var/run/docker.sock`) instead of a TCP port.
* Only users in the **docker group** are allowed to talk to this socket.

So if Jenkins tries to run `docker build` but Jenkins user isn't in the `docker` group, it gets:
```
permission denied while trying to connect to the Docker daemon socket
```

## 4. **The `usermod` Fix**
You ran:
```bash
sudo usermod -aG docker jenkins
sudo usermod -aG docker ubuntu
```

* This adds both **jenkins** and **ubuntu** users into the **docker group**.
* Now when Jenkins runs a job, it has the rights to run Docker commands.
* Without this, Jenkins would need `sudo` (which complicates automation).

👉 This step is **critical glue**: it allows Jenkins pipelines to build/push/run Docker containers.

## 5. **How They All Work Together**

**Flow:**
1. **You push code to GitHub.**
2. **Jenkins (on EC2)** pulls that code when you run a job.
3. Jenkins executes Docker commands (`docker build`, `docker run`, `docker push`).
4. Docker daemon (on EC2) builds/runs containers.
5. Containers expose apps → accessible on EC2's public IP.

## 6. **Who Controls What**
* **EC2:** Provides compute, networking, storage. Host for everything.
* **Jenkins:** Orchestrates workflow (build, test, deploy).
* **Docker:** Actually packages & runs your app.
* **usermod/docker group:** Grants Jenkins permission to control Docker on EC2.

## 🔹 Architecture Visualization

```
         ┌─────────────────────────────────┐
         │           AWS EC2 (Ubuntu)       │
         │                                  │
         │   ┌────────────┐    ┌─────────┐ │
You ───▶ │   │  Jenkins   │───▶│  Docker │ │───▶ [Container: Nginx + App]
         │   └────────────┘    └─────────┘ │
         │        │              ▲         │
         │        ▼              │         │
         │   /var/run/docker.sock│         │
         │      (requires        │         │
         │     usermod config)   │         │
         └─────────────────────────────────┘
```

## 🔹 Detailed Process Flow

### **Stage 1: Code Development & Version Control**
```
Developer → Code Changes → Git Push → GitHub Repository
```

### **Stage 2: Jenkins Pipeline Trigger**
```
GitHub Webhook/Manual Trigger → Jenkins Job Execution → EC2 Instance
```

### **Stage 3: Build Process**
```
Jenkins pulls code → Dockerfile processing → Docker build command → Container image
```

### **Stage 4: Docker Operations**
```
Docker daemon reads Dockerfile → Builds layers → Creates image → Stores locally
```

### **Stage 5: Deployment**
```
Docker run command → Container creation → Port mapping → Application accessible
```

## 🔹 Permission Architecture Deep Dive

### **Why Docker Socket Permissions Matter**
- Docker daemon runs as **root** by default
- `/var/run/docker.sock` is owned by **root:docker**
- Socket permissions: `srw-rw----` (660)
- Only **root** and **docker group** members can write to it

### **User Hierarchy**
```
┌─────────────┐
│    root     │ ← Full system access
├─────────────┤
│ docker grp  │ ← Can control Docker daemon
├─────────────┤
│   jenkins   │ ← Added to docker group via usermod
├─────────────┤
│   ubuntu    │ ← Default EC2 user, also in docker group
└─────────────┘
```

### **What Happens Without usermod**
```bash
jenkins@ec2:~$ docker ps
Got permission denied while trying to connect to the Docker daemon socket 
at unix:///var/run/docker.sock: Get http://%2Fvar%2Frun%2Fdocker.sock/v1.40/containers/json: 
dial unix /var/run/docker.sock: connect: permission denied
```

## 🔹 Security Considerations

### **Docker Group = Root Equivalent**
⚠️ **Important:** Adding a user to the docker group is equivalent to giving them root access because:
- Docker containers can mount the host filesystem
- Containers can run with `--privileged` flag
- Docker daemon runs as root

### **Best Practices**
- Use specific service accounts for Jenkins
- Implement proper IAM roles on AWS
- Consider using Docker-in-Docker (DinD) for better isolation
- Regularly audit group memberships

## 🔹 Troubleshooting Common Issues

### **Issue 1: Permission Denied**
```bash
# Problem
docker: permission denied while trying to connect to Docker daemon

# Solution
sudo usermod -aG docker $USER
newgrp docker  # Apply group changes without logout
```

### **Issue 2: Jenkins Service Restart Required**
```bash
# After usermod, restart Jenkins to pick up new group membership
sudo systemctl restart jenkins
```

### **Issue 3: Docker Daemon Not Running**
```bash
# Check Docker status
sudo systemctl status docker

# Start Docker if stopped
sudo systemctl start docker
sudo systemctl enable docker
```

## 🔹 Alternative Approaches

### **1. Rootless Docker**
```bash
# Install Docker in rootless mode (more secure)
curl -fsSL https://get.docker.com/rootless | sh
```

### **2. Docker-in-Docker (DinD)**
```yaml
# Use DinD in Jenkins pipeline
pipeline {
    agent {
        docker {
            image 'docker:dind'
            args '--privileged'
        }
    }
}
```

### **3. Kubernetes Integration**
- Use Jenkins Kubernetes plugin
- Run Jenkins agents as pods
- Better resource management and isolation

---

## 🚀 **Complete Setup Guide: Step-by-Step Implementation**

### **Prerequisites**
- AWS Account with EC2 access
- GitHub repository with your application code
- Basic understanding of Linux commands

### **Step 1: Launch and Configure EC2 Instance**

#### **1.1 Create EC2 Instance**
```bash
# Launch Ubuntu 22.04 LTS instance
# Instance type: t2.medium (minimum recommended for Jenkins + Docker)
# Security Group: Allow ports 22 (SSH), 8080 (Jenkins), 80 (HTTP), 443 (HTTPS)
```

#### **1.2 Connect to Instance**
```bash
# SSH into your EC2 instance
ssh -i your-key.pem ubuntu@your-ec2-public-ip

# Update system packages
sudo apt update && sudo apt upgrade -y
```

### **Step 2: Install and Configure Docker**

#### **2.1 Install Docker**
```bash
# Remove old Docker versions
sudo apt-get remove docker docker-engine docker.io containerd runc

# Install dependencies
sudo apt-get install apt-transport-https ca-certificates curl gnupg lsb-release

# Add Docker GPG key
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

# Add Docker repository
echo "deb [arch=amd64 signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Update package index
sudo apt-get update

# Install Docker Engine
sudo apt-get install docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Verify installation
sudo docker run hello-world
```

#### **2.2 Configure Docker**
```bash
# Start and enable Docker service
sudo systemctl start docker
sudo systemctl enable docker

# Add ubuntu user to docker group
sudo usermod -aG docker ubuntu

# Apply group changes
newgrp docker

# Verify Docker works without sudo
docker --version
docker ps
```

### **Step 3: Install and Configure Jenkins**

#### **3.1 Install Java (Jenkins prerequisite)**
```bash
# Install OpenJDK 17
sudo apt install openjdk-17-jdk -y

# Verify Java installation
java -version
```

#### **3.2 Install Jenkins**
```bash
# Add Jenkins GPG key
curl -fsSL https://pkg.jenkins.io/debian-stable/jenkins.io-2023.key | sudo tee /usr/share/keyrings/jenkins-keyring.asc > /dev/null

# Add Jenkins repository
echo deb [signed-by=/usr/share/keyrings/jenkins-keyring.asc] https://pkg.jenkins.io/debian-stable binary/ | sudo tee /etc/apt/sources.list.d/jenkins.list > /dev/null

# Update package index
sudo apt-get update

# Install Jenkins
sudo apt-get install jenkins

# Start and enable Jenkins
sudo systemctl start jenkins
sudo systemctl enable jenkins

# Check Jenkins status
sudo systemctl status jenkins
```

#### **3.3 Configure Jenkins Initial Setup**
```bash
# Get initial admin password
sudo cat /var/lib/jenkins/secrets/initialAdminPassword

# Access Jenkins web interface
# http://your-ec2-public-ip:8080
```

### **Step 4: Configure Jenkins-Docker Integration**

#### **4.1 Add Jenkins User to Docker Group**
```bash
# This is the CRITICAL step that enables Jenkins to use Docker
sudo usermod -aG docker jenkins

# Verify jenkins user is in docker group
groups jenkins

# Restart Jenkins to apply group changes
sudo systemctl restart jenkins
```

#### **4.2 Install Docker Pipeline Plugin in Jenkins**
1. Go to Jenkins Dashboard → Manage Jenkins → Plugins
2. Search for "Docker Pipeline"
3. Install without restart
4. Also install "GitHub Integration Plugin"

### **Step 5: Create Jenkins Pipeline**

#### **5.1 Create New Pipeline Job**
1. Jenkins Dashboard → New Item
2. Enter name → Select "Pipeline"
3. Configure GitHub repository connection
4. Set up webhook (optional)

#### **5.2 Sample Jenkinsfile**
```groovy
pipeline {
    agent any
    
    environment {
        IMAGE_NAME = "myapp"
        IMAGE_TAG = "latest"
        CONTAINER_NAME = "myapp-container"
    }
    
    stages {
        stage('Cleanup') {
            steps {
                script {
                    // Stop and remove existing container
                    sh '''
                        docker stop $CONTAINER_NAME || true
                        docker rm $CONTAINER_NAME || true
                        docker rmi $IMAGE_NAME:$IMAGE_TAG || true
                    '''
                }
            }
        }
        
        stage('Checkout') {
            steps {
                // Jenkins automatically checks out the repository
                echo 'Code checked out successfully'
            }
        }
        
        stage('Build Docker Image') {
            steps {
                script {
                    // Build Docker image
                    sh "docker build -t $IMAGE_NAME:$IMAGE_TAG ."
                }
            }
        }
        
        stage('Deploy Application') {
            steps {
                script {
                    // Run container
                    sh '''
                        docker run -d \
                        --name $CONTAINER_NAME \
                        -p 80:80 \
                        $IMAGE_NAME:$IMAGE_TAG
                    '''
                }
            }
        }
        
        stage('Verify Deployment') {
            steps {
                script {
                    // Check if container is running
                    sh 'docker ps | grep $CONTAINER_NAME'
                    
                    // Test application endpoint
                    sh 'curl -f http://localhost:80 || exit 1'
                }
            }
        }
    }
    
    post {
        always {
            // Clean up workspace
            cleanWs()
        }
        success {
            echo 'Pipeline completed successfully!'
        }
        failure {
            echo 'Pipeline failed!'
            // Optional: Send notifications
        }
    }
}
```

### **Step 6: Configure Security Groups and Networking**

#### **6.1 Update EC2 Security Group**
```bash
# Allow inbound traffic on required ports:
# Port 22: SSH access
# Port 8080: Jenkins web interface
# Port 80: Application access
# Port 443: HTTPS (if using SSL)
```

#### **6.2 Configure Elastic IP (Optional)**
```bash
# Allocate Elastic IP for consistent access
# Associate with your EC2 instance
```

### **Step 7: Testing and Verification**

#### **7.1 Test Docker Commands**
```bash
# Switch to jenkins user and test Docker
sudo su - jenkins
docker --version
docker ps
exit
```

#### **7.2 Run Pipeline Test**
1. Go to Jenkins Dashboard
2. Select your pipeline job
3. Click "Build Now"
4. Monitor console output
5. Verify application is accessible at `http://your-ec2-ip`

### **Step 8: Production Considerations**

#### **8.1 Security Hardening**
```bash
# Configure firewall
sudo ufw enable
sudo ufw allow 22
sudo ufw allow 8080
sudo ufw allow 80
sudo ufw allow 443

# Set up SSL certificates for Jenkins
# Configure reverse proxy with Nginx (optional)
```

#### **8.2 Backup and Monitoring**
```bash
# Set up Jenkins backup strategy
# Configure CloudWatch monitoring
# Set up log rotation
```

#### **8.3 Auto-scaling and High Availability**
- Consider using Application Load Balancer
- Set up Auto Scaling Groups
- Use Amazon ECS/EKS for container orchestration

---

## ✅ **In Summary**

* **EC2** = The server foundation
* **Jenkins** = Automation brain that orchestrates CI/CD
* **Docker** = Containerization platform that packages and runs your app
* **`usermod`** = The critical permission bridge that allows Jenkins to control Docker **without sudo**

This integration creates a powerful, automated deployment pipeline where code changes trigger builds, tests, and deployments seamlessly across your cloud infrastructure.


## Real life production

# 🔹 Real-Time Setup (Industry)
# 1. Kubernetes as the Host

Instead of 1 EC2 with Docker, you have a Kubernetes cluster.

Cluster = many nodes (worker EC2s, or managed like EKS/GKE/AKS).

Kubernetes schedules & runs your containers across the cluster.

So, the "host" is Kubernetes, not a single EC2.
Docker (or another container runtime like containerd) still runs underneath, but Kubernetes manages them.

# 2. Jenkins with Kubernetes

Jenkins doesn’t directly run docker run on EC2 anymore.

Instead, Jenkins:

Builds Docker images.

Pushes to registry (Docker Hub, ECR, etc.).

Applies Kubernetes manifests (kubectl apply -f deployment.yaml).

👉 Kubernetes then pulls the image and deploys it on the cluster automatically.

# 3. Advantages of Kubernetes

High availability: If 1 node dies, pods move to another.

Auto scaling: Can increase replicas if traffic spikes.

Service discovery & load balancing: Pods are load-balanced internally.

Rolling updates: New image versions can be deployed with zero downtime.

# 🔹 Comparison
Feature	Your Setup (EC2 + Docker)	Real Setup (Kubernetes)
Host	1 EC2	Cluster of nodes
Scaling	Manual (new container)	Automatic (replicas)
Failover	None	Pod rescheduling
Networking	Port mapping on EC2	Kubernetes Services/Ingress
Deploy method	docker run from Jenkins	kubectl apply from Jenkins
Best for	Learning, small projects	Production, large apps



.............................................................................................


## For saving docker hub credentials :

# use jenkins manager > credentials > global > add user with password >  add username and pswd :

pipeline {
    agent any

    stages {
        stage('Checkout') {
            steps {
                git branch: 'main', url: 'https://github.com/kashishver-ma/Cloud-learnings'
            }
        }
        
        stage('Show File') {
            steps {
                sh 'cat index.html'
            }
        }

        stage('Build Docker Image') {
            steps {
                sh 'docker build -t htmlapp:latest .'
            }
        }

        stage('Push to Docker Hub') {
            steps {
                withCredentials([usernamePassword(credentialsId: 'dockerhub', usernameVariable: 'DOCKER_USER', passwordVariable: 'DOCKER_PASS')]) {
                    sh '''
                        echo "$DOCKER_PASS" | docker login -u "$DOCKER_USER" --password-stdin
                        docker tag htmlapp:latest $DOCKER_USER/htmlapp:latest
                        docker push $DOCKER_USER/htmlapp:latest
                    '''
                }
            }
        }

        stage('Deploy') {
            steps {
                withCredentials([usernamePassword(credentialsId: 'dockerhub', usernameVariable: 'DOCKER_USER', passwordVariable: 'DOCKER_PASS')]) {
                    sh '''
                        docker rm -f htmlapp || true
                        docker run -d -p 8080:80 --name htmlapp $DOCKER_USER/htmlapp:latest
                    '''
                }
            }
        }
    }
}
 
